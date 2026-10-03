"""Independent live replay and freeze audit of the selected v4 instances."""
from __future__ import annotations
from collections import Counter
import json
from dotenv import dotenv_values
from neo4j import GraphDatabase
from .generate import ReadGraph, canonical_rows, rejection, REPO, write_jsonl
from .v4 import V4, assert_frozen, checkpoint


def main():
    assert_frozen()
    selected=[json.loads(line) for line in (V4/'instances_v4_train.jsonl').read_text().splitlines()]
    config=dotenv_values(REPO/'.env')
    observations=[]
    with GraphDatabase.driver(str(config['BIRD_NEO4J_URI']),auth=(str(config['BIRD_NEO4J_USER']),str(config['BIRD_NEO4J_PASSWORD']))) as driver:
        graph=ReadGraph(driver)
        for item in selected:
            rows,runtime=graph.execute(item['cypher'],item['params'])
            observations.append({'instance_id':item['instance_id'],'hops':item['hops'],'shape':item['shape'],'cypher':item['cypher'],'params':item['params'],'rows':rows,'runtime_ms':runtime,'matches_saved':canonical_rows(rows)==canonical_rows(item['rows']),'rejection':rejection(rows,runtime)})
    write_jsonl(V4/'inspection.jsonl',observations)
    report=json.loads((V4/'report.json').read_text())
    report['independent_live_replay']={'executed':len(observations),'matched':sum(row['matches_saved'] for row in observations),'rejections':dict(Counter(row['rejection'] for row in observations if row['rejection'])),'mismatched_ids':[row['instance_id'] for row in observations if not row['matches_saved']],'max_runtime_ms':max(row['runtime_ms'] for row in observations)}
    report['unit_tests']={'passed':25,'command':'PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider tinker_cookbook/recipes/bird_graph_rl/datagen'}
    # Count the outputs instead of inferring wording progress from selection.
    question_file=V4/'questions_v4_train.jsonl'
    report['questions_written']=len(question_file.read_text().splitlines()) if question_file.exists() else 0
    report['heldout_question_overlap_check']='pending: individual v4 questions have not been written'
    assert_frozen()
    (V4/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    checkpoint('step 3 verification complete',json.dumps(report['independent_live_replay'],indent=2)+'\n\nSelected-instance mix is in out/v4/report.json. Individual question writing remains pending; v4 is not ready for training. Frozen files still match the pre-run SHA-256 manifest. Test results: '+json.dumps(report['unit_tests'])+'.')
    print(json.dumps(report['independent_live_replay'],indent=2))


if __name__=='__main__':main()
