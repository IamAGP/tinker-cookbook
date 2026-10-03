"""Independent deterministic sample replay and complete artifact integrity audit."""
from __future__ import annotations
from collections import Counter, defaultdict
import json
import random

from dotenv import dotenv_values
from neo4j import GraphDatabase

from .generate import HERE, REPO, ReadGraph, canonical_rows, write_jsonl
from .structures import enumerate_structures, components
from .split import plan_split


def main() -> None:
    out = HERE/'out'
    report = json.loads((out/'report.json').read_text())
    structures = [json.loads(line) for line in (out/'structures.jsonl').read_text().splitlines()]
    instances = [json.loads(line) for line in (out/'instances.jsonl').read_text().splitlines()]
    known = {s.structure_id:s for s in enumerate_structures()}
    by_structure = defaultdict(list)
    strata = defaultdict(list)
    for instance in instances:
        by_structure[instance['structure_id']].append(instance)
        strata[instance['hops']].append(instance)
        assert instance['n_rows'] == len(instance['rows'])
        assert 1 <= instance['n_rows'] <= 200
        assert instance['runtime_ms'] <= 5000
        assert any(v is not None for r in instance['rows'] for v in r.values())
        assert instance['cypher'] == known[instance['structure_id']].render()
    assert len({i['instance_id'] for i in instances}) == len(instances)
    for structure in structures:
        group = by_structure[structure['structure_id']]
        assert len(group) == structure['n_instances'] <= 12
        assert structure['signature'] == known[structure['structure_id']].signature
        assert len({json.dumps(i['params'],sort_keys=True) for i in group}) == len(group)
        assert len({canonical_rows(i['rows']) for i in group}) > 1
        if structure['split'] == 'heldout_structure':
            assert {i['split'] for i in group} == {'heldout_structure'}
        else:
            assert {i['split'] for i in group} <= {'train','heldout_instance'}
            assert sum(i['split'] == 'heldout_instance' for i in group) <= 2
            assert any(i['split'] == 'train' for i in group)
    plan=plan_split([known[s['structure_id']] for s in structures],report['seed'])
    assert {s['structure_id']:s['split'] for s in structures}==plan.assignments
    assert all(s['novelty']==plan.novelty.get(s['structure_id']) for s in structures)
    rng = random.Random(report['seed'])
    sample = []
    for hops in sorted(strata):
        sample.extend(rng.sample(sorted(strata[hops],key=lambda i:i['instance_id']),min(12,len(strata[hops]))))
    # Add at least one of every retained aggregation, extra, and actual rendering mode.
    seen = {known[i['structure_id']].mode for i in sample}
    for i in instances:
        mode = known[i['structure_id']].mode
        if mode not in seen:
            sample.append(i)
            seen.add(mode)
    # Cover every retained path, including shared-root branches.
    seen_paths = {known[i['structure_id']].path for i in sample}
    for i in instances:
        path = known[i['structure_id']].path
        if path not in seen_paths:
            sample.append(i)
            seen_paths.add(path)
    # Replay every pilot binding too, independently of the stratified sample.
    pilot_path = out/'pilot_questions.jsonl'
    pilot_ids = {json.loads(line)['instance_id'] for line in pilot_path.read_text().splitlines()} if pilot_path.exists() else set()
    already_sampled = {i['instance_id'] for i in sample}
    sample.extend(i for i in instances if i['instance_id'] in pilot_ids and i['instance_id'] not in already_sampled)
    assert pilot_ids <= {i['instance_id'] for i in sample}
    config = dotenv_values(REPO/'.env')
    checks = []
    with GraphDatabase.driver(str(config['BIRD_NEO4J_URI']),
         auth=(str(config['BIRD_NEO4J_USER']),str(config['BIRD_NEO4J_PASSWORD']))) as driver:
        graph = ReadGraph(driver)
        names = {str(r['name']) for r in graph.names()}
        for i in sample:
            structure = known[i['structure_id']]
            rows,runtime = graph.execute(i['cypher'],i['params'])
            assert canonical_rows(rows) == canonical_rows(i['rows']),i['instance_id']
            assert runtime <= 5000,i['instance_id']
            if structure.mode in ('top','bottom','argmax'):
                k = i['params']['k']
                probe,_ = graph.execute(structure.render(probe=True),dict(i['params'],probe_k=k+1))
                assert len(probe) <= k or probe[k-1][structure.sort_column] != probe[k][structure.sort_column]
            assert structure.path.labels[0]!='User' or all(i['params'][key] in names for key in ('name','other_name') if key in i['params'])
            checks.append({'instance_id':i['instance_id'],'hops':i['hops'],'mode':structure.mode,
                           'n_rows':len(rows),'runtime_ms':round(runtime,3),
                           'rows_preview':rows[:3],'exact_replay':True})
    write_jsonl(out/'inspection.jsonl',checks)
    summary = {'artifact_integrity':'passed','sample_size':len(checks),
               'sample_by_hop':dict(Counter(c['hops'] for c in checks)),
               'sample_modes':sorted(seen),'sample_paths':len(seen_paths),'pilot_replays':len(pilot_ids),'all_replays_match':True}
    (out/'inspection_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))


if __name__ == '__main__':
    main()
