"""Audit authored bindings and replay a deterministic question sample read-only."""
from __future__ import annotations
import importlib
import json
import random
from collections import Counter
from dotenv import dotenv_values
from neo4j import GraphDatabase
from .generate import HERE,REPO,ReadGraph,canonical_rows,write_jsonl
from .structures import enumerate_structures
from .question_authoring import polish

def main():
    out=HERE/'out'
    queue=[json.loads(l) for l in (out/'question_queue.jsonl').read_text().splitlines()]
    questions=[json.loads(l) for l in (out/'questions.jsonl').read_text().splitlines()]
    # Refresh already written strings from their individual authoring sources after
    # correcting the shared date/subject grammar. No new question is generated here.
    authored=[]
    for batch in range(1,len(questions)//100+1):
        authored.extend(importlib.import_module(f'{__package__}.questions_batch{batch:02}').q)
    assert len(authored)==len(questions)
    for n,q in enumerate(questions):
        assert q['instance_id']==queue[n]['instance_id']
        assert set(q)=={'instance_id','question'}
        q['question']=polish(authored[n],queue[n])
    assert len({q['instance_id'] for q in questions})==len(questions)
    assert len({q['question'] for q in questions})==len(questions)
    write_jsonl(out/'questions.jsonl',questions)
    known={s.structure_id:s for s in enumerate_structures()}
    instances={i['instance_id']:i for i in [json.loads(l) for l in (out/'instances.jsonl').read_text().splitlines()]}
    rng=random.Random(20261003)
    sample=rng.sample(questions,min(12,len(questions)))
    seen={known[instances[q['instance_id']]['structure_id']].mode for q in sample}
    for q in questions:
        mode=known[instances[q['instance_id']]['structure_id']].mode
        if mode not in seen:sample.append(q);seen.add(mode)
    config=dotenv_values(REPO/'.env');checks=[]
    with GraphDatabase.driver(str(config['BIRD_NEO4J_URI']),auth=(str(config['BIRD_NEO4J_USER']),str(config['BIRD_NEO4J_PASSWORD']))) as driver:
        graph=ReadGraph(driver)
        for q in sample:
            i=instances[q['instance_id']]
            rows,runtime=graph.execute(i['cypher'],i['params'])
            assert canonical_rows(rows)==canonical_rows(i['rows']),i['instance_id']
            checks.append(dict(q,mode=known[i['structure_id']].mode,rows_preview=rows[:2],exact_replay=True,runtime_ms=round(runtime,3)))
    write_jsonl(out/'question_inspection.jsonl',checks)
    summary={'questions_total':len(questions),'questions_by_split':dict(Counter(instances[q['instance_id']]['split'] for q in questions)),'sample_replays':len(checks),'all_replays_match':True,'sample_modes':sorted(seen)}
    (out/'question_audit.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))
    for check in checks[:8]:print(json.dumps(check,ensure_ascii=False))

if __name__=='__main__':main()
