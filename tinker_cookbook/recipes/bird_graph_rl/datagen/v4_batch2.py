"""Select the disjoint second batch without editing the accepted first batch."""
from __future__ import annotations
from collections import Counter,defaultdict
import hashlib,json,random,re
from dotenv import dotenv_values
from neo4j import GraphDatabase
from .generate import ReadGraph,REPO,canonical_rows,rejection,write_jsonl,HERE
from .structures import Structure,Path,components
from .hints import hint
from .v4 import V4,OUT,TARGETS,SEED,features,forbidden,load,assert_frozen


def checkpoint(title,data):
    for target in (V4/'CHECKPOINT.md',HERE/'README.md'):
        with target.open('a') as f:f.write('\n## '+title+'\n\n'+json.dumps(data,indent=2)+'\n')


def content_key(item):return item['cypher'],json.dumps(item['params'],sort_keys=True)


def select_and_verify():
    assert_frozen()
    protected=['instances_v4_train.jsonl','structures_v4_train.jsonl','questions_v4_train.jsonl','new_structures.json']
    hashes={name:hashlib.sha256((V4/name).read_bytes()).hexdigest() for name in protected}
    first=[json.loads(line) for line in (V4/protected[0]).read_text().splitlines()]
    ids={i['instance_id'] for i in first};keys={content_key(i) for i in first};prior=Counter(i['structure_id'] for i in first)
    old_structs,_=load();old={s['structure_id']:s for s in old_structs}
    structs={s['structure_id']:s for s in [json.loads(line) for line in (V4/'pool_structures.jsonl').read_text().splitlines()]}
    structs.update({s['structure_id']:s for s in [json.loads(line) for line in (V4/'extra_structures_batch2.jsonl').read_text().splitlines()]} if (V4/'extra_structures_batch2.jsonl').exists() else {})
    pool=[];seen=set()
    source=[json.loads(line) for line in (V4/'pool.jsonl').read_text().splitlines()]
    if (V4/'extra_pool_batch2.jsonl').exists():source.extend(json.loads(line) for line in (V4/'extra_pool_batch2.jsonl').read_text().splitlines())
    for item in source:
        key=content_key(item)
        if item['instance_id'] not in ids and key not in keys and key not in seen and prior[item['structure_id']]<5:
            pool.append(item);seen.add(key)
    size=280
    fs=[features(i,structs[i['structure_id']] if i['instance_id'].startswith('v4_') else old[i['structure_id']]) for i in pool]
    axes=[(kind,name) for kind,values in TARGETS.items() for name in values]
    vectors=[[int(name in shape[kind]) if isinstance(shape[kind],list) else int(name==shape[kind]) for kind,name in axes] for shape in fs]
    targets=[TARGETS[k][n]*size/100 for k,n in axes]
    quotas={'none':154,'count':70,'sum':17,'count distinct':8,'avg':4,'max':3,'min':3,'more than one aggregate':21}
    assert sum(quotas.values())==size
    groups=defaultdict(list)
    for j,shape in enumerate(fs):groups[shape['aggregation']].append(j)
    rng=random.Random(SEED+1);selected=set();per=Counter(prior);counts=[0]*len(axes)
    def loss(values):
        score=0
        for j,(kind,name) in enumerate(axes):
            if kind=='extras' and name=='negation':continue
            delta=values[j]-targets[j]
            if kind=='ordering' and name in ('n-th ranked','order with no limit'):delta=max(0,values[j]-2)
            excess=max(0,abs(delta)-size*.025)
            score+=delta*delta+100*excess*excess
            if kind=='ordering' and name in ('n-th ranked','order with no limit'):score+=100000*max(0,values[j]-2)**2
            if kind=='extras' and name=='distinct projection':score+=100000*max(0,values[j]-25)**2
        return score
    for aggregation,amount in quotas.items():
        candidates=groups[aggregation][:];rng.shuffle(candidates)
        for unused in range(amount):
            available=[j for j in candidates if j not in selected and per[pool[j]['structure_id']]<5]
            if not available:raise ValueError('Insufficient remaining '+aggregation+' capacity')
            j=min(available,key=lambda j:loss([a+b for a,b in zip(counts,vectors[j])]))
            selected.add(j);per[pool[j]['structure_id']]+=1;counts=[a+b for a,b in zip(counts,vectors[j])]
    best=loss(counts)
    for iteration in range(160000):
        before=rng.choice(tuple(selected));after=rng.choice(groups[fs[before]['aggregation']])
        if after in selected:continue
        a,b=pool[before]['structure_id'],pool[after]['structure_id']
        if a!=b and per[b]>=5:continue
        candidate=[n-x+y for n,x,y in zip(counts,vectors[before],vectors[after])];cost=loss(candidate)
        if cost<best or cost==best and rng.random()<.02:
            selected.remove(before);selected.add(after);per[a]-=1;per[b]+=1;counts=candidate;best=cost
    chosen=[]
    for j in sorted(selected,key=lambda j:(fs[j]['depth'],pool[j]['structure_id'],pool[j]['instance_id'])):
        item=dict(pool[j]);item['shape']=fs[j]
        s=structs[item['structure_id']]
        if item['instance_id'].startswith('v4_'):
            basic=Structure(Path(tuple(s['base_path_labels']),tuple(tuple(e) for e in s['base_path_edges'])),item['base_mode'],s.get('anchor_kind','id'))
            value=hint(basic,item['instance_id'])
            if value:
                style=item['v4_style']
                if style in ('count','group','group_comment','projection'):
                    mapping={'score':('score','Score'),'reputation':('reputation','Reputation'),'count':('stored tag usage count','Count'),'displayName':('display name','DisplayName'),'tagName':('tag name','TagName'),'title':('title','Title'),'body':('body','Body'),'text':('comment text','Text'),'creationDate':('creation date','CreationDate'),'closedDate':('closing date','ClosedDate'),'lastEditDate':('last edit date','LastEditDate'),'location':('location','Location'),'userId':('user ID','Id'),'postId':('post ID','Id'),'commentId':('comment ID','Id')}
                    fields=set(re.findall(r'\.([A-Za-z][A-Za-z0-9]*)',item['cypher']))
                    parts=[phrase+' refers to '+source for field,(phrase,source) in mapping.items() if field in fields]
                    if 'creationDate' in fields:
                        for match in re.finditer(r'n(\d+)\.creationDate',item['cypher']):
                            if basic.path.labels[int(match.group(1))] in ('Post','Question','Answer'):parts.append('post creation date refers to CreaionDate')
                    if style=='count':parts.append('the count refers to qualifying entities, each counted once')
                    if style=='group':parts.append('the post count refers to posts per selected author; users without matching posts are absent')
                    if style=='group_comment':parts.append('the comment count refers to comments per selected author; users without matching comments are absent')
                    if style=='projection':parts.append('the list refers to distinct displayed names or text, without ordering')
                    if 'left(' in item['cypher']:parts.append('the preview refers to the first 120 characters')
                    value='; '.join(parts)+'.'
                item['hint']=value
            else:item.pop('hint',None)
        chosen.append(item)
    actual={k:Counter() for k in TARGETS}
    for item in chosen:
        for k,v in item['shape'].items():actual[k].update(v if isinstance(v,list) else [v])
    mix={k:{n:{'count':actual[k][n],'achieved_percent':100*actual[k][n]/size,'target_percent':target} for n,target in values.items()} for k,values in TARGETS.items()}
    chosen_structs={i['structure_id']:structs[i['structure_id']] for i in chosen}
    held={s['signature'] for s in old_structs if s['split']=='heldout_structure'};blocked=forbidden(old_structs)
    class Signature:
        def __init__(self,text):self.signature=text
    sig_collisions=[sid for sid,s in chosen_structs.items() if s['signature'] in held]
    introduced=set().union(*(components(Signature(s['signature'])) for s in chosen_structs.values()))&blocked
    assert not sig_collisions and not introduced
    report={'status':'selected; verifying against live graph','selected_instances':len(chosen),'questions_written':0,'mix':mix,'structure_counts':{'reused':sum(sid in old for sid in chosen_structs),'new':sum(sid not in old for sid in chosen_structs)},'checks':{'disjoint_instance_ids':not ids&{i['instance_id'] for i in chosen},'disjoint_query_parameter_pairs':not keys&{content_key(i) for i in chosen},'combined_max_per_structure':max(per.values()),'no_heldout_signature':not sig_collisions,'no_heldout_component_introduced':not introduced},'hints':{'with_hint':sum('hint' in i for i in chosen),'share':sum('hint' in i for i in chosen)/len(chosen)},'first_batch_hashes':hashes,'declared_shortfalls':['Negation is held out entirely and omitted.'],'spec_arithmetic_note':{'first_requested':len(first),'second_requested':size,'combined_requested':len(first)+size,'stated_total_in_D2':592,'interpretation':'Follow the explicit batch sizes; the stated total differs from their sum.'}}
    write_jsonl(V4/'instances_v4_train_batch2.jsonl',chosen);write_jsonl(V4/'structures_v4_train_batch2.jsonl',list(chosen_structs.values()))
    (V4/'report_batch2.json').write_text(json.dumps(report,indent=2)+'\n');checkpoint('Second batch selection checkpoint',report)
    config=dotenv_values(REPO/'.env');inspection=[]
    with GraphDatabase.driver(str(config['BIRD_NEO4J_URI']),auth=(str(config['BIRD_NEO4J_USER']),str(config['BIRD_NEO4J_PASSWORD']))) as driver:
        graph=ReadGraph(driver)
        for item in chosen:
            rows,runtime=graph.execute(item['cypher'],item['params'])
            again,_=graph.execute(item['cypher'],item['params'])
            inspection.append({'instance_id':item['instance_id'],'matches_saved':canonical_rows(rows)==canonical_rows(item['rows']),'repeat_matches':canonical_rows(rows)==canonical_rows(again),'rejection':rejection(rows,runtime),'runtime_ms':runtime,'rows':rows})
    write_jsonl(V4/'inspection_batch2.jsonl',inspection)
    report['verification']={'executed':len(inspection),'matched':sum(r['matches_saved'] for r in inspection),'stable':sum(r['repeat_matches'] for r in inspection),'rejections':dict(Counter(r['rejection'] for r in inspection if r['rejection'])),'mismatched_ids':[r['instance_id'] for r in inspection if not r['matches_saved'] or not r['repeat_matches']]}
    assert not report['verification']['rejections'] and not report['verification']['mismatched_ids']
    report['checks']['first_batch_unchanged']=all(hashlib.sha256((V4/name).read_bytes()).hexdigest()==value for name,value in hashes.items())
    assert report['checks']['first_batch_unchanged'];assert_frozen()
    report['status']='selected and live-verified; individual question wording pending'
    (V4/'report_batch2.json').write_text(json.dumps(report,indent=2)+'\n');checkpoint('Second batch verification checkpoint',report)
    print(json.dumps({k:v for k,v in report.items() if k!='first_batch_hashes'},indent=2))


if __name__=='__main__':select_and_verify()
