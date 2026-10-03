"""Literal binding and disk checkpoints for individually composed v4 questions."""
from __future__ import annotations
from collections import Counter
import hashlib
import json
import re
from .generate import HERE
from .structures import Structure, Path, enumerate_structures
from .pilot import subject
from .v4 import V4, OUT, assert_frozen

INSTANCES=V4/'instances_v4_train.jsonl'
INSTANCE_SHA=hashlib.sha256(INSTANCES.read_bytes()).hexdigest()
ROWS=[json.loads(line) for line in INSTANCES.read_text().splitlines()]
STRUCTS={s['structure_id']:s for s in [json.loads(line) for line in (V4/'structures_v4_train.jsonl').read_text().splitlines()]}
OLD={s.structure_id:s for s in enumerate_structures()}
ORDER={'lookup':0,'projection':1,'count':2,'group':3,'rank':4,'ratio':5,'old':6}
QUEUE=sorted(ROWS,key=lambda i:(ORDER[i.get('v4_style','old')],OLD[i['structure_id']].mode if not i.get('v4_style') else '',i['structure_id'],i['instance_id']))
KNOWN={}
for i in QUEUE:
    s=STRUCTS[i['structure_id']]
    KNOWN[i['instance_id']]=Structure(Path(tuple(s['base_path_labels']),tuple(tuple(e) for e in s['base_path_edges'])),i['base_mode'],s.get('anchor_kind','id')) if i.get('v4_style') else OLD[i['structure_id']]


def structure(index):return KNOWN[QUEUE[index]['instance_id']]
def p(index,key):return QUEUE[index]['params'][key]
def d(index):
    s=structure(index)
    phrase=subject(s,QUEUE[index]['params'])
    if 'lower' in QUEUE[index]['params'] and QUEUE[index]['params'].get('upper')==QUEUE[index]['params']['lower']:
        number=str(QUEUE[index]['params']['lower']);phrase=phrase.replace('between '+number+' and '+number+' inclusive','exactly '+number)
    phrase=re.sub(r'(the answer with ID \d+) respond\b',r'\1 responds',phrase)
    if s.label=='User' and s.mode=='year':
        base=phrase.split(', created in years')[0]
        role='have '+base[len('users with '):] if base.startswith('users with ') else 'are '+base
        phrase=f"users who joined in years {p(index,'year')} through {p(index,'end_year')} inclusive and {role}"
    return phrase if phrase.startswith('the ') else 'the '+phrase

def m(index):return 'stored tag usage count' if structure(index).metric=='count' else structure(index).metric

def display(index):
    return {'User':'display names','Tag':'tag names','Comment':'comment previews (the first 120 characters of the text)','Answer':'answer previews (the first 120 characters of the body)','Post':'titles (or the first 120 body characters for untitled posts)','Question':'question titles (or the first 120 body characters when untitled)'}[structure(index).label]

def f(index):
    row=QUEUE[index]['rows'][0]
    parts=[display(index)]
    if len(row)>=2:parts.append(m(index))
    if len(row)>=3:parts.append('locations' if structure(index).label=='User' else 'creation dates' if structure(index).label=='Comment' else 'view counts')
    return ', '.join(parts[:-1])+' and '+parts[-1] if len(parts)>1 else parts[0]

def root(index):
    s=structure(index)
    label=s.path.labels[0]
    # The root-only path exists in the schema catalog for these grouped users.
    return subject(Structure(Path((label,)),'detail',s.anchor),QUEUE[index]['params'])

def posts(index):
    mode=structure(index).mode
    return 'posts with no recorded title' if mode=='null' else 'posts with a recorded title' if mode=='not_null' else 'posts'

def gf(index):
    width=len(QUEUE[index]['rows'][0])
    return 'only the per-user counts' if width==1 else 'display names and post counts' if width==2 else 'display names, post counts and reputation'

def associated(index):
    s=structure(index)
    return {'User':'users','Post':'posts','Question':'questions','Answer':'answers','Comment':'comments','Tag':'tags','Vote':'votes','PostHistory':'revision entries','Badge':'badges'}[s.path.labels[s.previous]]

def comparison(index):
    s=structure(index)
    return s.description.replace('the selected users','each named user'),repr(p(index,'name')),repr(p(index,'other_name'))


def append_batch(start,sentences):
    assert_frozen()
    assert hashlib.sha256(INSTANCES.read_bytes()).hexdigest()==INSTANCE_SHA
    destination=V4/'questions_v4_train.jsonl'
    existing=[json.loads(line) for line in destination.read_text().splitlines()] if destination.exists() else []
    assert len(existing)==start
    written={q['instance_id'] for q in existing}
    held_ids={json.loads(line)['instance_id'] for line in (OUT/'instances.jsonl').read_text().splitlines() if json.loads(line)['split']!='train'}
    held_questions={q['question'] for q in [json.loads(line) for line in (OUT/'questions.jsonl').read_text().splitlines()] if q['instance_id'] in held_ids}
    records=[]
    for index,sentence in enumerate(sentences,start):
        item=QUEUE[index]
        literals={}
        for literal in item['params'].values():
            if isinstance(literal,str) and repr(literal) in sentence:
                token=f'__LITERAL{len(literals)}__';literals[token]=repr(literal);sentence=sentence.replace(repr(literal),token)
        sentence=re.sub(r'\b(distinct|different|unique|highest-scoring|highest-reputation|best-scoring|most reputable) the ',r'\1 ',sentence)
        sentence=re.sub(r'(\b\d+) the (?=users|tags|posts|questions|answers|comments|authors)',r'\1 ',sentence)
        audited=sentence
        for token,literal in literals.items():sentence=sentence.replace(token,literal)
        assert not re.search(r'\b(node|edge|relationship|route|connection|path|value|entity_id|member|standing points)\b',audited,re.I),(index,audited)
        assert not re.search(r'\b[a-z]+[A-Z][a-zA-Z]*\b',audited),(index,audited)
        assert not re.search(r'\b(?:post_text|user_name|associated_count|positive_percentage|identity|extra_field)\b',audited),(index,audited)
        assert item['instance_id'] not in written
        assert sentence not in held_questions
        records.append({'instance_id':item['instance_id'],'question':sentence})
    assert len({q['question'] for q in existing+records})==len(existing)+len(records)
    with destination.open('a') as stream:
        for record in records:stream.write(json.dumps(record,ensure_ascii=False)+'\n')
        stream.flush()
    summary={'batch_start':start,'batch_written':len(records),'questions_written':len(existing)+len(records),'selected_instances':len(QUEUE),'selected_instance_sha256':INSTANCE_SHA,'next_queue_index':len(existing)+len(records)}
    (V4/'question_checkpoint.json').write_text(json.dumps(summary,indent=2)+'\n')
    for target in (V4/'CHECKPOINT.md',HERE/'README.md'):
        with target.open('a') as stream:stream.write('\n## Individually authored v4 question batch\n\n'+json.dumps(summary,indent=2)+'\n\nContinue with the frozen authoring queue. Instances and hints remain unchanged.\n')
    print(json.dumps(summary))


if __name__=='__main__':
    for index,item in enumerate(QUEUE):
        s=structure(index)
        print(index,item.get('v4_style','old'),s.mode,s.label,len(item['rows'][0]),m(index),s.path.hops,s.path.labels,s.anchor)
