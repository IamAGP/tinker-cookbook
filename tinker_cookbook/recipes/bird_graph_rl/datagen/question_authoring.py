"""Binding and checkpoint helpers for individually authored question batches."""
from __future__ import annotations
import json
import re
from collections import Counter
from .generate import HERE
from .structures import enumerate_structures
from .pilot import subject

OUT=HERE/'out'
QUEUE=[json.loads(l) for l in (OUT/'question_queue.jsonl').read_text().splitlines()]
KNOWN={s.structure_id:s for s in enumerate_structures()}

def d(index):
    i=QUEUE[index]
    return subject(KNOWN[i['structure_id']],i['params'])

def m(index):
    s=KNOWN[QUEUE[index]['structure_id']]
    return 'stored tag usage count' if s.metric=='count' else s.metric

def p(index,key): return QUEUE[index]['params'][key]

def field(index):
    label=KNOWN[QUEUE[index]['structure_id']].label
    return {'User':'display name','Tag':'tag name','Comment':'first 120 characters of the comment text','Answer':'first 120 characters of the answer body','Post':'title, using the first 120 body characters if no title is recorded','Question':'title, using the first 120 body characters if no title is recorded'}[label]

def associated(index):
    s=KNOWN[QUEUE[index]['structure_id']]
    return {'User':'users','Post':'posts','Question':'questions','Answer':'answers','Comment':'comments','Tag':'tags','Vote':'votes','PostHistory':'revision entries','Badge':'badges'}[s.path.labels[s.previous]]

def comparison(index):
    i=QUEUE[index];s=KNOWN[i['structure_id']]
    return s.description.replace('the selected users','each named user'),repr(i['params']['name']),repr(i['params']['other_name'])

def append_batch(start, sentences):
    assert len(sentences)==100
    existing=[json.loads(l) for l in (OUT/'questions.jsonl').read_text().splitlines()] if (OUT/'questions.jsonl').exists() else []
    written={q['instance_id'] for q in existing}
    records=[]
    for index,sentence in enumerate(sentences,start):
        instance=QUEUE[index]
        assert instance['instance_id'] not in written
        audited=sentence
        for literal in instance['params'].values():
            if isinstance(literal,str):audited=audited.replace(repr(literal),'')
        assert not re.search(r'\b(node|edge|relationship|route|connection|path|value|entity_id)\b',audited,re.I),(index,audited)
        assert not re.search(r'\b[a-z]+[A-Z][a-zA-Z]*\b',audited),(index,audited)
        assert len(sentence)>15
        records.append({'instance_id':instance['instance_id'],'question':sentence})
    assert len({q['question'] for q in existing+records})==len(existing)+len(records)
    with (OUT/'questions.jsonl').open('a') as stream:
        for q in records:stream.write(json.dumps(q,ensure_ascii=False)+'\n')
    all_instances={i['instance_id']:i for i in [json.loads(l) for l in (OUT/'instances.jsonl').read_text().splitlines()]}
    counts=Counter(all_instances[q['instance_id']]['split'] for q in existing+records)
    summary={'batch_start':start,'batch_size':len(records),'questions_total':len(existing)+len(records),'questions_by_split':dict(counts)}
    (OUT/'question_checkpoint.json').write_text(json.dumps(summary,indent=2)+'\n')
    with (HERE/'README.md').open('a') as stream:
        stream.write('\n## Question batch checkpoint\n\n'+json.dumps(summary,sort_keys=True)+'\n\nQuestions are separately authored in the numbered batch module, with shared helpers only for exact data literals and subject descriptions. Next: continue the persisted training queue before either held-out split.\n')
    print(json.dumps(summary))
