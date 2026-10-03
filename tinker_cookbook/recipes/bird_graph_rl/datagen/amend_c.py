"""Execute only new C3 candidates, merge verified data, and apply C2 exactly."""
from __future__ import annotations
from collections import Counter, defaultdict
from dataclasses import fields
import json
import logging
import random

from dotenv import dotenv_values
from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError

from .generate import (HERE, REPO, Instance, ReadGraph, parameter_sets, generate_structure,
                       stable_seed, write_jsonl, naturalness_report)
from .structures import enumerate_structures, PROPERTIES
from .split import plan_split, split_instances


def main() -> None:
    out=HERE/'out'
    report=json.loads((out/'report.json').read_text())
    old_structures=[json.loads(l) for l in (out/'structures.jsonl').read_text().splitlines()]
    existing=[json.loads(l) for l in (out/'instances.jsonl').read_text().splitlines()]
    seed=report['seed']
    additions_path=out/'c3_additions.jsonl'
    additions=[json.loads(l) for l in additions_path.read_text().splitlines()] if additions_path.exists() else []
    seen={s['structure_id'] for s in old_structures}|{i['structure_id'] for i in additions}
    catalog=enumerate_structures()
    new=[s for s in catalog if s.structure_id not in seen and s.mode in ('nth','conditional_count','conditional_sum','projection')]
    rejects=Counter()
    logging.basicConfig(level=logging.INFO)
    handler=logging.FileHandler(out/'c3_debug.log',mode='a'); handler.setLevel(logging.DEBUG)
    from .generate import LOGGER
    LOGGER.setLevel(logging.DEBUG); LOGGER.addHandler(handler); LOGGER.propagate=False
    config=dotenv_values(REPO/'.env')
    with GraphDatabase.driver(str(config['BIRD_NEO4J_URI']),auth=(str(config['BIRD_NEO4J_USER']),str(config['BIRD_NEO4J_PASSWORD']))) as driver:
        graph=ReadGraph(driver)
        names={r['anchor']:str(r['name']) for r in graph.names()}
        pools={}
        for index,s in enumerate(new):
            if s.path.pattern not in pools:
                pool=graph.root_pool(s.path)
                random.Random(stable_seed(seed,s.path.pattern)).shuffle(pool)
                pools[s.path.pattern]=pool[:144]
            pool=pools[s.path.pattern]
            if s.mode in ('conditional_count','conditional_sum') and s.path.hops:
                key=PROPERTIES[s.path.labels[0]][0]
                rows,_=graph.execute(f'CYPHER 25 MATCH REPEATABLE ELEMENTS {s.path.pattern} WHERE n0.{key} IN $anchors AND {s.measure} IS NOT NULL RETURN DISTINCT n0.{key} AS anchor, {s.measure} AS measurement ORDER BY anchor, measurement LIMIT 5000',{'anchors':[r['anchor'] for r in pool]},cap=None)
                measured=defaultdict(list)
                for row in rows: measured[row['anchor']].append(str(row['measurement']))
                pool=[dict(r,condition_values='|'.join(measured[r['anchor']])) for r in pool]
            params=parameter_sets(s,pool,names,seed,48)
            local=Counter()
            kept=generate_structure(graph,s,params,set(names.values()),local)
            rejects.update(local)
            records=[i.record() for i in kept]
            with additions_path.open('a') as f:
                for record in records: f.write(json.dumps(record,sort_keys=True,ensure_ascii=False)+'\n')
            additions.extend(records)
            print(json.dumps({'candidate':index+1,'of':len(new),'mode':s.mode,'kept':len(kept),'rejections':dict(local)}),flush=True)
    merged={i['instance_id']:i for i in existing+additions}
    instances=list(merged.values())
    known={s.structure_id:s for s in catalog}
    counts=Counter(i['structure_id'] for i in instances)
    ss=[known[sid] for sid in sorted(counts)]
    plan=plan_split(ss,seed,dict(counts))
    groups=defaultdict(list)
    for i in instances: groups[i['structure_id']].append(i)
    structure_records=[]
    for s in ss:
        group=groups[s.structure_id]
        split=split_instances([i['instance_id'] for i in group],plan.assignments[s.structure_id],stable_seed(seed,s.structure_id))
        for i in group: i['split']=split[i['instance_id']]
        structure_records.append({'structure_id':s.structure_id,'signature':s.signature,'hops':s.path.hops,
            'n_instances':len(group),'training_instances':sum(i['split']=='train' for i in group),
            'split':plan.assignments[s.structure_id],'intent':s.intent,'anchor_kind':s.anchor,'mode':s.mode,
            'novelty':plan.novelty.get(s.structure_id),'unseen_components':plan.unseen_components.get(s.structure_id,[])})
    training=[i for i in instances if i['split']=='train']
    assert all(6<=s['training_instances']<=12 for s in structure_records if s['split']=='train')
    assert 2*sum(i['hops']<=1 for i in training)>=len(training)
    assert 100*sum(i['hops']>=3 for i in training)<=15*len(training)
    write_jsonl(out/'structures.jsonl',structure_records)
    write_jsonl(out/'instances.jsonl',instances)
    previous_deep={s['structure_id'] for s in old_structures if s['split']=='train' and s['hops']>=3}
    report.update({'totals':{'enumerated_structures':len(catalog),'kept_structures':len(ss),'kept_instances':len(instances)},
        'structures_by_hop':dict(Counter(str(s.path.hops) for s in ss)),
        'instances_by_hop':dict(Counter(str(i['hops']) for i in instances)),
        'structures_by_split':dict(Counter(plan.assignments.values())),
        'instances_by_split':dict(Counter(i['split'] for i in instances)),
        'structures_by_aggregation':dict(Counter(s.aggregation for s in ss)),
        'structures_by_extras':dict(Counter(e for s in ss for e in s.extras)),
        'instances_by_aggregation':dict(Counter(known[i['structure_id']].aggregation for i in instances)),
        'instances_by_extras':dict(Counter(e for i in instances for e in known[i['structure_id']].extras)),
        'novelty_counts':dict(Counter(plan.novelty.values())),'held_components':plan.held_components,
        'naturalness_removals':naturalness_report(),'c3_rejections':dict(rejects),
        'c3_added_structures':len({i['structure_id'] for i in additions}),
        'c3_added_instances':len(additions),'deep_structures_moved':sum(plan.assignments[sid]=='heldout_structure' for sid in previous_deep),
        'instances_by_split_hop':{part:{str(h):sum(i['split']==part and i['hops']==h for i in instances) for h in range(5)} for part in ('train','heldout_instance','heldout_structure')},
        'structures_by_split_hop':{part:{str(h):sum(s['split']==part and s['hops']==h for s in structure_records) for h in range(5)} for part in ('train','heldout_structure')},
        'c2':{'training_shallow_share':sum(i['hops']<=1 for i in training)/len(training),'training_deep_share':sum(i['hops']>=3 for i in training)/len(training),'training_structure_min':min(s['training_instances'] for s in structure_records if s['split']=='train'),'training_structure_max':max(s['training_instances'] for s in structure_records if s['split']=='train')}})
    report['anchor_instances']=dict(Counter(known[i['structure_id']].anchor for i in instances))
    report['return_shapes']=dict(Counter(str(len(i['rows'][0]))+' columns' for i in instances))
    report['numeric_id_anchor_share']=sum('anchor' in i['params'] for i in instances)/len(instances)
    report['single_column_share']=sum(len(i['rows'][0])==1 for i in instances)/len(instances)
    report['single_value_alias_share']=sum(list(i['rows'][0])==['value'] for i in instances)/len(instances)
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    checkpoint={'step':'C2/C3 applied; replay next','totals':report['totals'],'c2':report['c2'],
                'split_hops':report['instances_by_split_hop'],'moved_deep':report['deep_structures_moved']}
    (out/'checkpoint_c.json').write_text(json.dumps(checkpoint,indent=2)+'\n')
    readme=HERE/'README.md'
    readme.write_text('# Amendments C checkpoint\n\nC2 rebalanced and C3 new shallow shapes executed; exact current counts:\n\n```json\n'+json.dumps(checkpoint,indent=2)+'\n```\n\nNext: independent replay, hints refresh, then append individually authored\nquestions in priority order, checkpointing after each batch. Earlier sections\nbelow describe the previous revision. C1 withdraws the return-width concern.\n\n'+readme.read_text())
    print(json.dumps(checkpoint,indent=2),flush=True)


if __name__=='__main__': main()
