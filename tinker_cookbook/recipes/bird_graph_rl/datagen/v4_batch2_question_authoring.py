"""Bind separately written second-batch sentences to the verified frozen selection."""
from __future__ import annotations
from collections import Counter
import hashlib,json,re
import importlib.util
from . import v4_question_authoring as first_binding
# Load a private binding context; importing this module cannot redirect the first-batch helpers.
spec=importlib.util.spec_from_file_location(__package__+"._batch2_binding",first_binding.__file__)
assert spec is not None and spec.loader is not None
b=importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)
from .v4 import V4,OUT,HERE,assert_frozen
from .structures import Structure,Path
from .v4_batch2 import checkpoint

b.INSTANCES=V4/'instances_v4_train_batch2.jsonl'
b.INSTANCE_SHA=hashlib.sha256(b.INSTANCES.read_bytes()).hexdigest()
b.ROWS=[json.loads(line) for line in b.INSTANCES.read_text().splitlines()]
b.STRUCTS={s['structure_id']:s for s in [json.loads(line) for line in (V4/'structures_v4_train_batch2.jsonl').read_text().splitlines()]}
order=dict(b.ORDER,group_comment=3)
b.QUEUE=sorted(b.ROWS,key=lambda i:(order[i.get('v4_style','old')],b.OLD[i['structure_id']].mode if not i.get('v4_style') else '',i['structure_id'],i['instance_id']))
b.KNOWN={}
for item in b.QUEUE:
    s=b.STRUCTS[item['structure_id']]
    b.KNOWN[item['instance_id']]=Structure(Path(tuple(s['base_path_labels']),tuple(tuple(e) for e in s['base_path_edges'])),item['base_mode'],s.get('anchor_kind','id')) if item.get('v4_style') else b.OLD[item['structure_id']]
QUEUE=b.QUEUE;d=b.d;f=b.f;m=b.m;p=b.p;structure=b.structure;root=b.root;comparison=b.comparison;associated=b.associated


def posts(index):return 'comments' if QUEUE[index].get('v4_style')=='group_comment' else b.posts(index)
def gf(index):return b.gf(index).replace('post counts','comment counts') if QUEUE[index].get('v4_style')=='group_comment' else b.gf(index)


def append_batch(start,sentences):
    assert_frozen()
    report=json.loads((V4/'report_batch2.json').read_text())
    assert all(hashlib.sha256((V4/name).read_bytes()).hexdigest()==sha for name,sha in report['first_batch_hashes'].items())
    destination=V4/'questions_v4_train_batch2.jsonl'
    existing=[json.loads(line) for line in destination.read_text().splitlines()] if destination.exists() else []
    assert len(existing)==start
    first=[json.loads(line) for line in (V4/'questions_v4_train.jsonl').read_text().splitlines()]
    old_instances={i['instance_id']:i for i in [json.loads(line) for line in (OUT/'instances.jsonl').read_text().splitlines()]}
    held=[q for q in [json.loads(line) for line in (OUT/'questions.jsonl').read_text().splitlines()] if old_instances[q['instance_id']]['split']!='train']
    normalize=lambda text:re.sub(r'\s+',' ',text).strip().casefold()
    other={normalize(q['question']) for q in existing+first+held}
    records=[]
    for index,sentence in enumerate(sentences,start):
        audited=sentence.replace(d(index),'__SUBJECT__')
        for literal in QUEUE[index]['params'].values():
            if isinstance(literal,str):audited=audited.replace(repr(literal),'__LITERAL__')
        assert not re.search(r'\b(node|edge|relationship|route|connection|path|value|entity_id|member|standing points|post_text|user_name|associated_count|positive_percentage|identity|extra_field)\b',audited,re.I),(index,audited)
        assert not re.search(r'\b[a-z]+[A-Z][a-zA-Z]*\b',audited),(index,audited)
        sentence=re.sub(r'\b(distinct|different|unique|highest-scoring|highest-reputation) the ',r'\1 ',sentence)
        assert normalize(sentence) not in other
        other.add(normalize(sentence));records.append({'instance_id':QUEUE[index]['instance_id'],'question':sentence})
    with destination.open('a') as stream:
        for q in records:stream.write(json.dumps(q,ensure_ascii=False)+'\n')
        stream.flush()
    assert hashlib.sha256(b.INSTANCES.read_bytes()).hexdigest()==b.INSTANCE_SHA
    report['questions_written']=len(existing)+len(records)
    report['status']='second-batch wording in progress' if report['questions_written']<len(QUEUE) else 'second-batch questions complete; final audit pending'
    report['question_checkpoint']={'next_queue_index':report['questions_written'],'instance_sha256':b.INSTANCE_SHA,'batch_start':start,'batch_written':len(records)}
    (V4/'report_batch2.json').write_text(json.dumps(report,indent=2)+'\n')
    checkpoint('Second-batch individually authored question checkpoint',report['question_checkpoint']|{'questions_written':report['questions_written'],'selected_instances':len(QUEUE)})
    print(json.dumps(report['question_checkpoint']|{'questions_written':report['questions_written']}))


if __name__=='__main__':
    for index,item in enumerate(QUEUE):
        s=structure(index)
        print(index,item.get('v4_style','old'),s.mode,s.label,len(item['rows'][0]),m(index),s.path.hops,s.anchor)
