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
    s=KNOWN[i['structure_id']]
    phrase=subject(s,i['params'])
    if s.label=='User' and s.mode=='year':
        base=phrase.split(', created in years')[0]
        role='have '+base[len('users with '):] if base.startswith('users with ') else 'are '+base
        phrase=f"users who joined in years {i['params']['year']} through {i['params']['end_year']} inclusive and {role}"
    phrase=re.sub(r'(the answer with ID \d+) respond\b',r'\1 responds',phrase)
    return phrase if phrase.startswith('the ') else 'the '+phrase

def m(index):
    s=KNOWN[QUEUE[index]['structure_id']]
    return 'stored tag usage count' if s.metric=='count' else s.metric

def p(index,key): return QUEUE[index]['params'][key]

def field(index):
    label=KNOWN[QUEUE[index]['structure_id']].label
    return {'User':'display name','Tag':'tag name','Comment':'first 120 characters of the comment text','Answer':'first 120 characters of the answer body','Post':'title (or the first 120 body characters when untitled)','Question':'title (or the first 120 body characters when untitled)'}[label]

def associated(index):
    s=KNOWN[QUEUE[index]['structure_id']]
    return {'User':'users','Post':'posts','Question':'questions','Answer':'answers','Comment':'comments','Tag':'tags','Vote':'votes','PostHistory':'revision entries','Badge':'badges'}[s.path.labels[s.previous]]

def comparison(index):
    i=QUEUE[index];s=KNOWN[i['structure_id']]
    return s.description.replace('the selected users','each named user'),repr(i['params']['name']),repr(i['params']['other_name'])

def polish(sentence,instance):
    literals={}
    for literal in instance['params'].values():
        if isinstance(literal,str) and repr(literal) in sentence:
            token=f'__LITERAL{len(literals)}__';literals[token]=repr(literal)
            sentence=sentence.replace(repr(literal),token)
    sentence=re.sub(r'\b(distinct|different|unique|highest-scoring|highest-reputation|best-scoring|most reputable) the ',r'\1 ',sentence)
    sentence=re.sub(r'(\b\d+) the (?=users|tags|posts|questions|answers|comments|authors)',r'\1 ',sentence)
    sentence=re.sub(r'\b1 distinct qualifying (posts|questions|answers|comments|users|tags|votes)\b',lambda match:'1 distinct qualifying '+match.group(1)[:-1],sentence)
    for token,literal in literals.items():sentence=sentence.replace(token,literal)
    return sentence

def append_batch(start, sentences):
    assert 1<=len(sentences)<=100
    existing=[json.loads(l) for l in (OUT/'questions.jsonl').read_text().splitlines()] if (OUT/'questions.jsonl').exists() else []
    written={q['instance_id'] for q in existing}
    records=[]
    for index,sentence in enumerate(sentences,start):
        instance=QUEUE[index]
        sentence=polish(sentence,instance)
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
        stream.write('\n## Question batch checkpoint\n\n'+json.dumps(summary,sort_keys=True)+'\n\nQuestions are separately authored in the numbered batch module, with shared helpers only for exact data literals and subject descriptions. Follow the latest owner priority and frozen queue for the next batch.\n')
    print(json.dumps(summary))
