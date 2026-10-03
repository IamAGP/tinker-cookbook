"""Read-only replay of appended questions and exact frozen-input integrity checks."""
from __future__ import annotations
import hashlib
import importlib
import json
import logging
import argparse
from collections import Counter,defaultdict
from dotenv import dotenv_values
from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError
from .generate import HERE,REPO,ReadGraph,canonical_rows,write_jsonl,LOGGER
from .held_question_authoring import QUEUE,KNOWN
from .question_authoring import polish


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--refresh-authored-tail',action='store_true',help='Apply individual language edits only to the appended held-out records')
    args=parser.parse_args()
    out=HERE/'out'
    frozen=json.loads((out/'heldout_frozen.json').read_text())
    assert hashlib.sha256((out/'instances.jsonl').read_bytes()).hexdigest()==frozen['instances_sha256']
    assert hashlib.sha256((out/'structures.jsonl').read_bytes()).hexdigest()==frozen['structures_sha256']
    data=(out/'questions.jsonl').read_bytes()
    assert hashlib.sha256(data[:frozen['original_questions_bytes']]).hexdigest()==frozen['original_questions_sha256']
    questions=[json.loads(l) for l in data.splitlines()]
    before=frozen['original_questions_count'];new=questions[before:]
    assert len(new)==len(QUEUE)
    assert len({q['instance_id'] for q in questions})==len(questions)
    assert len({q['question'] for q in questions})==len(questions)
    authored=[]
    for batch in range(1,8):authored.extend(importlib.import_module(f'{__package__}.held_questions_batch{batch:02}').q)
    assert len(authored)==len(new)
    if args.refresh_authored_tail:
        for question,instance,sentence in zip(new,QUEUE,authored,strict=True):
            assert question['instance_id']==instance['instance_id']
            question['question']=polish(sentence,instance)
        pending=out/'questions.pending.jsonl'
        pending.write_bytes(data[:frozen['original_questions_bytes']]+b''.join((json.dumps(q,sort_keys=True,ensure_ascii=False)+'\n').encode() for q in new))
        assert hashlib.sha256(pending.read_bytes()[:frozen['original_questions_bytes']]).hexdigest()==frozen['original_questions_sha256']
        pending.replace(out/'questions.jsonl')
        assert len({q['question'] for q in questions})==len(questions)
    instances={i['instance_id']:i for i in [json.loads(l) for l in (out/'instances.jsonl').read_text().splitlines()]}
    structures={s['structure_id']:s for s in [json.loads(l) for l in (out/'structures.jsonl').read_text().splitlines()]}
    for question,instance,sentence in zip(new,QUEUE,authored,strict=True):
        assert set(question)=={'instance_id','question'}
        assert question['instance_id']==instance['instance_id']
        assert question['question']==polish(sentence,instance)
        assert instance['split']!='train'
    hi={i['instance_id'] for i in instances.values() if i['split']=='heldout_instance'}
    sample=json.loads((out/'heldout_structure_sample.json').read_text())
    assert {q['instance_id'] for q in new if instances[q['instance_id']]['split']=='heldout_instance'}==hi
    assert {q['instance_id'] for q in new if instances[q['instance_id']]['split']=='heldout_structure'}==set(sample['instance_ids'])
    selected=defaultdict(list)
    for iid in sample['instance_ids']:selected[instances[iid]['structure_id']].append(instances[iid])
    assert {sid for sid in selected if structures[sid]['novelty']=='novel_component'}=={sid for sid,s in structures.items() if s['novelty']=='novel_component'}
    for sid,group in selected.items():
        if structures[sid]['novelty']=='novel_component':
            assert 1<=len(group)<=4
            assert len({json.dumps(i['params'],sort_keys=True) for i in group})==len(group)
        else:assert len(group)==1
    logging.basicConfig(level=logging.INFO)
    handler=logging.FileHandler(out/'heldout_verify.log');LOGGER.addHandler(handler);LOGGER.setLevel(logging.DEBUG)
    config=dotenv_values(REPO/'.env');checks=[];failures=[]
    with GraphDatabase.driver(str(config['BIRD_NEO4J_URI']),auth=(str(config['BIRD_NEO4J_USER']),str(config['BIRD_NEO4J_PASSWORD']))) as driver:
        graph=ReadGraph(driver)
        for number,q in enumerate(new,1):
            i=instances[q['instance_id']]
            try:
                rows,runtime=graph.execute(i['cypher'],i['params'])
                match=canonical_rows(rows)==canonical_rows(i['rows'])
                check=dict(q,split=i['split'],hops=i['hops'],mode=KNOWN[i['structure_id']].mode,novelty=structures[i['structure_id']]['novelty'],runtime_ms=round(runtime,3),exact_replay=match,rows_preview=rows[:2])
                if not match:failures.append({'instance_id':i['instance_id'],'reason':'saved_result_mismatch'})
                checks.append(check)
            except Neo4jError as error:
                failures.append({'instance_id':i['instance_id'],'reason':error.code})
            if number%100==0:print(json.dumps({'replays_attempted':number,'matching':sum(c['exact_replay'] for c in checks),'failures':len(failures)}),flush=True)
    write_jsonl(out/'heldout_question_inspection.jsonl',checks)
    write_jsonl(out/'heldout_question_failures.jsonl',failures)
    # Identify uninformative additional thresholds without altering frozen inputs.
    incompatible=[];redundant=[]
    for q in new:
        i=instances[q['instance_id']];s=KNOWN[i['structure_id']];p=i['params']
        if s.mode in ('conditional_count','conditional_sum') and s.anchor=='range':
            if p['condition']>p['upper']:incompatible.append(i['instance_id'])
            elif p['condition']<=p['lower']:redundant.append(i['instance_id'])
    summary={'artifact_integrity':'passed','frozen_instances_unchanged':True,'frozen_structures_and_splits_unchanged':True,'original_question_prefix_unchanged':True,
             'questions_total':len(questions),'questions_by_split':dict(Counter(instances[q['instance_id']]['split'] for q in questions)),
             'new_questions':len(new),'replays_attempted':len(new),'matching_replays':sum(c['exact_replay'] for c in checks),'replay_failures':len(failures),
             'structure_sample_counts_by_novelty':sample['counts_by_novelty'],'structure_sample_counts_by_hop':sample['counts_by_hop'],'structure_sample_counts_by_novelty_hop':sample['counts_by_novelty_hop'],
             'sample_structures_by_novelty':dict(Counter(structures[sid]['novelty'] for sid in selected)),
             'component_sample_instances_per_structure':dict(Counter(len(group) for sid,group in selected.items() if structures[sid]['novelty']=='novel_component')),
             'conditional_range_incompatible_thresholds':len(incompatible),'conditional_range_redundant_thresholds':len(redundant),
             'uninformative_condition_instance_ids':{'incompatible':incompatible,'redundant':redundant}}
    (out/'heldout_question_audit.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2),flush=True)
    for check in checks[::max(1,len(checks)//12)]:print(json.dumps(check,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
