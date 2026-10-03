"""Execute and filter query-first data; no evaluation or training APIs are used."""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import logging
import math
from pathlib import Path
import random
import re
import time

from dotenv import dotenv_values
from neo4j import Driver, GraphDatabase, READ_ACCESS
from neo4j.exceptions import Neo4jError

from .split import split_instances, split_structures
from .structures import JSONScalar, PROPERTIES, Path as QueryPath, Structure, enumerate_structures

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
LOGGER = logging.getLogger('bird_datagen')
Params = dict[str, JSONScalar]
Rows = list[dict[str, JSONScalar]]


def stable_seed(seed: int, key: str) -> int:
    return int.from_bytes(hashlib.sha256(f'{seed}:{key}'.encode()).digest()[:8],'big')


def canonical_rows(rows: Rows) -> str:
    """Order-insensitive multiset, retaining duplicates and column identity."""
    return json.dumps(sorted(rows,key=lambda r:json.dumps(r,sort_keys=True)),sort_keys=True,
                      separators=(',',':'),ensure_ascii=False,allow_nan=False)


class ReadGraph:
    """Fixed read queries in explicit read transactions; never commit a transaction."""
    def __init__(self, driver: Driver) -> None:
        self.driver = driver

    def execute(self, cypher: str, params: Params | dict[str,list[JSONScalar]] | None = None,
                cap: int | None = 201, timeout: float = 5.0) -> tuple[Rows,float]:
        # No CALL/procedures, LOAD CSV or graph mutation clauses in this generator.
        if re.search(r'\b(CREATE|MERGE|SET|DELETE|REMOVE|DROP|LOAD|CALL|FOREACH)\b',cypher,re.I):
            raise ValueError('non-read clause blocked')
        start = time.perf_counter()
        rows: Rows = []
        with self.driver.session(database='neo4j',default_access_mode=READ_ACCESS) as session:
            with session.begin_transaction(timeout=timeout,metadata={'app':'bird-stage-a'}) as tx:
                result = tx.run(cypher,params or {})
                for record in result:
                    row: dict[str,JSONScalar] = {}
                    for key,value in record.items():
                        if value is not None and not isinstance(value,(str,int,float,bool)):
                            raise TypeError(f'Unsupported scalar type: {type(value).__name__}')
                        if isinstance(value,float) and not math.isfinite(value):
                            raise ValueError('nonfinite result')
                        row[key] = value
                    rows.append(row)
                    if cap is not None and len(rows) >= cap:
                        break
                # Context manager rolls back: read queries have no writes to commit.
        return rows,(time.perf_counter()-start)*1000

    def root_pool(self, path: QueryPath) -> Rows:
        key, metric, _, _ = PROPERTIES[path.labels[0]]
        first = QueryPath(path.labels,path.edges[:1]).pattern
        return self.execute(
            f'CYPHER 25 MATCH {first} RETURN DISTINCT n0.{key} AS anchor, '
            f'n0.{metric} AS metric ORDER BY anchor',cap=None,timeout=30)[0]

    def names(self) -> Rows:
        return self.execute('CYPHER 25 MATCH (u:User) WITH u.displayName AS name, '
                            'count(*) AS n, min(u.userId) AS anchor WHERE n = 1 AND name IS NOT NULL '
                            'RETURN name, anchor ORDER BY anchor',cap=None,timeout=30)[0]


def rejection(rows: Rows, runtime_ms: float) -> str | None:
    if runtime_ms > 5000:
        return 'runtime_over_5s'
    if not 1 <= len(rows) <= 200:
        return 'row_count'
    if all(value is None for row in rows for value in row.values()):
        return 'all_null'
    return None


def boundary_tie(rows: Rows, k: int) -> bool:
    return len(rows) > k and rows[k-1]['value'] == rows[k]['value']


@dataclass
class Instance:
    instance_id: str
    structure_id: str
    split: str
    hops: int
    cypher: str
    params: Params
    n_rows: int
    rows: Rows
    runtime_ms: float

    def record(self) -> dict[str, object]:
        return dict(vars(self))


def parameter_sets(structure: Structure, pool: Rows, names: dict[JSONScalar,str],
                   seed: int, max_attempts: int) -> list[Params]:
    rng = random.Random(stable_seed(seed,structure.structure_id))
    candidates = list(pool)
    rng.shuffle(candidates)
    if structure.mode in ('named','comparison'):
        candidates = [row for row in candidates if row['anchor'] in names]
    candidates = candidates[:max_attempts]
    other_names = sorted(names.values())
    result: list[Params] = []
    for row in candidates:
        if structure.path.hops:
            params: Params = {'anchor':row['anchor']}
        else:
            metric = row['metric']
            if not isinstance(metric,(int,float)):
                continue
            upper_values = sorted({r['metric'] for r in pool if isinstance(r['metric'],(int,float)) and r['metric'] >= metric})
            params = {'lower':metric,'upper':rng.choice(upper_values)}
        if structure.mode in ('top','bottom','argmax'):
            params['k'] = rng.choice([3,5,10]) if structure.mode == 'top' else 1
        if structure.mode == 'having':
            params['threshold'] = rng.choice([1,2,3])
        if structure.mode == 'year':
            years = sorted(int(y) for y in str(row.get('years') or '').split('|') if y)
            if not years:
                continue
            params['year'] = rng.choice(years)
            params['end_year'] = rng.choice([y for y in years if y >= params['year']])
        if structure.mode in ('contains','starts'):
            # Tokens measured from the graph, passed separately in the pool.
            tokens = str(row.get('texts') or '').split('|')
            tokens = [token for token in tokens if token]
            if not tokens:
                continue
            params['text'] = rng.choice(tokens)
        if structure.mode in ('named','comparison'):
            params = {'name':names[row['anchor']]}
            if structure.mode == 'comparison':
                alternatives = [name for name in other_names if name != params['name']]
                params['other_name'] = rng.choice(alternatives)
        result.append(params)
    # Distinct full parameter values within a structure, including numeric ranges.
    return list({json.dumps(p,sort_keys=True):p for p in result}.values())


def enrich_texts(graph: ReadGraph, structure: Structure, pool: Rows) -> Rows:
    if structure.mode not in ('contains','starts','year'):
        return pool
    root_key = PROPERTIES[structure.path.labels[0]][0]
    end = structure.endpoint
    text_key = 'displayName' if structure.label == 'User' else 'tagName' if structure.label == 'Tag' else 'title'
    # Temporal bounds and text are sampled from the graph, not invented vocabulary.
    if structure.mode == 'year':
        field, expression, output_key = 'creationDate', f'{end}.creationDate.year', 'years'
    else:
        field, expression, output_key = text_key, f'left({end}.{text_key}, 4)', 'texts'
    rows,_ = graph.execute(f'CYPHER 25 MATCH {structure.path.pattern} '
                           f'WHERE n0.{root_key} IN $anchors AND {end}.{field} IS NOT NULL '
                           f'RETURN DISTINCT n0.{root_key} AS anchor, {expression} AS text '
                           'ORDER BY anchor, text LIMIT 5000',
                           {'anchors':[r['anchor'] for r in pool]},cap=None)
    by_anchor: dict[JSONScalar,list[str]] = {}
    for row in rows:
        by_anchor.setdefault(row['anchor'],[]).append(str(row['text']))
    return [dict(row,**{output_key:'|'.join(by_anchor.get(row['anchor'],[]))}) for row in pool]


def generate_structure(graph: ReadGraph, structure: Structure, params_list: list[Params],
                       names: set[str], rejects: Counter[str]) -> list[Instance]:
    valid: list[Instance] = []
    answers: set[str] = set()
    n_valid = 0
    for params in params_list:
        if any(str(params[key]) not in names for key in ('name','other_name') if key in params):
            rejects['ambiguous_name'] += 1
            continue
        cypher = structure.render()
        try:
            rows,runtime = graph.execute(cypher,params)
            reason = rejection(rows,runtime)
            if reason is None and structure.mode in ('top','bottom','argmax'):
                k = int(params['k'])
                probe,probe_ms = graph.execute(structure.render(probe=True),dict(params,probe_k=k+1))
                if probe_ms > 5000:
                    reason = 'runtime_over_5s'
                elif boundary_tie(probe,k):
                    reason = 'cut_boundary_tie'
                elif canonical_rows(rows) != canonical_rows(probe[:k]):
                    reason = 'unstable_result'
        except Neo4jError as error:
            reason = 'runtime_over_5s' if 'TimedOut' in str(error.code) else 'execution_error'
            # Exception messages may include server details; log only code and structure/params.
            LOGGER.debug('%s error_code=%s params=%s',structure.structure_id,error.code,
                         json.dumps(params,sort_keys=True))
        if reason:
            rejects[reason] += 1
            LOGGER.debug('%s reject=%s params=%s',structure.structure_id,reason,
                         json.dumps(params,sort_keys=True))
            continue
        n_valid += 1
        key = canonical_rows(rows)
        answers.add(key)
        iid = 'i_' + hashlib.sha256((structure.structure_id+json.dumps(params,sort_keys=True)).encode()).hexdigest()[:20]
        instance = Instance(iid,structure.structure_id,'',structure.path.hops,cypher,params,
                            len(rows),rows,round(runtime,3))
        if len(valid) < 12:
            valid.append(instance)
        elif len(answers) == 2 and len({canonical_rows(i.rows) for i in valid}) == 1:
            valid[-1] = instance
        if len(valid) == 12 and len(answers) > 1:
            break
    if len(answers) <= 1:
        rejects['trivial_constant_answer'] += n_valid
        LOGGER.debug('%s dropped_constant candidates=%d valid=%d',structure.structure_id,
                     len(params_list),len(valid))
        return []
    return valid


def write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text(''.join(json.dumps(row,sort_keys=True,ensure_ascii=False,allow_nan=False)+'\n'
                            for row in records))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed',type=int,default=20261003)
    parser.add_argument('--attempts',type=int,default=96)
    parser.add_argument('--limit-structures',type=int,default=0,help='Smoke run only')
    args = parser.parse_args()
    out = HERE/'out'
    out.mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(message)s')
    handler = logging.FileHandler(out/'debug.log',mode='w')
    handler.setLevel(logging.DEBUG)
    LOGGER.addHandler(handler)
    LOGGER.setLevel(logging.DEBUG)
    LOGGER.propagate = False
    config = dotenv_values(REPO/'.env')
    all_structures = enumerate_structures()
    if args.limit_structures:
        all_structures = all_structures[:args.limit_structures]
    instances: list[Instance] = []
    kept_structures: list[Structure] = []
    per_structure: list[dict[str,object]] = []
    rejected: Counter[str] = Counter({key:0 for key in ('execution_error','runtime_over_5s',
        'row_count','all_null','cut_boundary_tie','unstable_result','ambiguous_name',
        'trivial_constant_answer','parameter_sampling_error','no_sampled_parameters')})
    with GraphDatabase.driver(str(config['BIRD_NEO4J_URI']),
        auth=(str(config['BIRD_NEO4J_USER']),str(config['BIRD_NEO4J_PASSWORD']))) as driver:
        graph = ReadGraph(driver)
        names = {row['anchor']:str(row['name']) for row in graph.names()}
        pools: dict[str,Rows] = {}
        for index,structure in enumerate(all_structures):
            pool_key = structure.path.pattern
            if pool_key not in pools:
                pool = graph.root_pool(structure.path)
                random.Random(stable_seed(args.seed,pool_key)).shuffle(pool)
                pools[pool_key] = pool[:args.attempts*3]
            pool = pools[pool_key]
            local: Counter[str] = Counter()
            try:
                enriched = enrich_texts(graph,structure,pool)
                params = parameter_sets(structure,enriched,names,args.seed,args.attempts)
                if not params:
                    local['no_sampled_parameters'] += 1
                kept = generate_structure(graph,structure,params,set(names.values()),local)
            except Neo4jError as error:
                LOGGER.debug('%s sampling_error=%s',structure.structure_id,error.code)
                local['parameter_sampling_error'] += 1
                kept = []
            rejected.update(local)
            per_structure.append({'structure_id':structure.structure_id,'mode':structure.mode,
                'hops':structure.path.hops,'n_instances':len(kept),'rejections':dict(local)})
            if kept:
                kept_structures.append(structure)
                instances.extend(kept)
            LOGGER.debug('%s done mode=%s kept=%d rejects=%s',structure.structure_id,
                         structure.mode,len(kept),dict(local))
            if (index+1)%10 == 0:
                print(f'{index+1}/{len(all_structures)} structures attempted; '
                      f'{len(kept_structures)} retained; {len(instances)} instances',flush=True)
    assignments = split_structures(kept_structures,args.seed)
    for structure in kept_structures:
        group = [i for i in instances if i.structure_id == structure.structure_id]
        splits = split_instances([i.instance_id for i in group],assignments[structure.structure_id],
                                stable_seed(args.seed,structure.structure_id))
        for instance in group:
            instance.split = splits[instance.instance_id]
    write_jsonl(out/'structures.jsonl',[
        {'structure_id':s.structure_id,'signature':s.signature,'hops':s.path.hops,
         'n_instances':sum(i.structure_id == s.structure_id for i in instances),
         'split':assignments[s.structure_id]} for s in kept_structures])
    write_jsonl(out/'instances.jsonl',[i.record() for i in instances])
    structure_hops = Counter(str(s.path.hops) for s in kept_structures)
    report = {'seed':args.seed,'max_attempts_per_structure':args.attempts,
        'totals':{'enumerated_structures':len(all_structures),'kept_structures':len(kept_structures),
                  'kept_instances':len(instances)},
        'structures_by_hop':dict(sorted(structure_hops.items())),
        'instances_by_hop':dict(sorted(Counter(str(i.hops) for i in instances).items())),
        'structures_by_aggregation':dict(sorted(Counter(s.aggregation for s in kept_structures).items())),
        'structures_by_extras':dict(sorted(Counter(e for s in kept_structures for e in s.extras).items())),
        'instances_by_aggregation':dict(sorted(Counter(next(s.aggregation for s in kept_structures if s.structure_id == i.structure_id) for i in instances).items())),
        'instances_by_extras':dict(sorted(Counter(e for i in instances for s in kept_structures if s.structure_id == i.structure_id for e in s.extras).items())),
        'instances_by_split':dict(sorted(Counter(i.split for i in instances).items())),
        'structures_by_split':dict(sorted(Counter(assignments.values()).items())),
        'rejections':dict(rejected),'per_structure':per_structure,
        'comparison_semantics':'order-insensitive multiset with named columns',
        'targets_met':len(kept_structures)>=150 and len(instances)>=1500
          and sum(s.path.hops <= 1 for s in kept_structures)/max(1,len(kept_structures)) <= .35
          and set(structure_hops) == {'0','1','2','3','4'}}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k != 'per_structure'},indent=2),flush=True)


if __name__ == '__main__':
    main()
