"""Build an isolated second training pool without touching frozen stage-A outputs."""
from __future__ import annotations
import argparse
from collections import Counter,defaultdict
from dataclasses import dataclass
from functools import cached_property
import hashlib,json,logging,random,re
from dotenv import dotenv_values
from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError
from .generate import HERE,REPO,ReadGraph,canonical_rows,rejection,parameter_sets,stable_seed,write_jsonl,LOGGER
from .structures import Structure,Path,paths,PROPERTIES,components,enumerate_structures
from .hints import hint

OUT=HERE/'out';V4=OUT/'v4';SEED=20261003
TARGETS={'aggregation':{'none':55,'count':25,'sum':7,'count distinct':3,'avg':3,'max':2,'min':1,'more than one aggregate':5},'ordering':{'none':83,'top 1':14,'top-k':1,'n-th ranked':0,'order with no limit':0},'grouping':{'yes':10},'extras':{'none':72,'distinct projection':9,'ratio':8,'conditional aggregate':8,'negation':3,'comparison of two named entities':2,'having':1,'existence':1},'columns':{'one':84,'two':12,'three or more':4},'depth':{'0-1':70,'2':20,'3-4':10}}

def checkpoint(step,text):
    with (HERE/'README.md').open('a') as f:f.write('\n## Amendment D checkpoint: '+step+'\n\n'+text+'\n')

def frozen():return {str(p.relative_to(OUT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.rglob('*') if p.is_file() and V4 not in p.parents}

def assert_frozen():assert frozen()==json.loads((V4/'frozen_manifest.json').read_text())

def load():
    ss=[json.loads(l) for l in (OUT/'structures.jsonl').read_text().splitlines()];ii=[json.loads(l) for l in (OUT/'instances.jsonl').read_text().splitlines()]
    return ss,ii

def forbidden(ss):return {c for s in ss if s['novelty']=='novel_component' for c in s['unseen_components']}

@dataclass(frozen=True)
class Variant:
    base:Structure
    style:str
    @cached_property
    def signature(self):
        sig=json.loads(self.base.signature)
        if self.style in ('lookup','projection','count'):
            sig['ordering']='none';sig['grouping']='none'
            sig['aggregation']=[{'lookup':'none','projection':'none','count':'count'}[self.style],sig['aggregation'][1]]
            sig['extras']=['DISTINCT projection'] if self.style=='projection' else []
        elif self.style=='group':
            sig['ordering']='none';sig['grouping']='User';sig['aggregation']=['count','Post'];sig['extras']=[]
        return json.dumps(sig,sort_keys=True,separators=(',',':'))
    @cached_property
    def structure_id(self):return 's_'+hashlib.sha256(self.signature.encode()).hexdigest()[:16]
    def render(self,width=1,probe=False):
        s=self.base
        if self.style in ('ratio','rank'): 
            query=s.render(probe=probe)
            if self.style=='rank' and not probe:
                query=query.replace(f'RETURN {s.display[1]}, {s.sort_column} ',f'RETURN {s.display[1]} ')
            return query
        prefix=s.render().split('WITH DISTINCT')[0]
        display,column=s.display;ident=s.identity;measurement=s.measure
        if self.style=='count':return prefix+f'RETURN count({s.endpoint}) AS {s.label.lower()}_count'
        if self.style=='group':
            query=prefix+'WITH n0 AS person, count(n1) AS post_count '
            cols=['post_count'] if width==1 else ['person.displayName AS user_name','post_count']
            if width>=3:cols.append('person.reputation AS reputation')
            return query+'RETURN '+', '.join(cols)
        if self.style=='projection':return prefix+f'RETURN DISTINCT {display} AS {column}'
        query=prefix+f'WITH DISTINCT {ident} AS identity, {display} AS {column}, {measurement} AS measurement'
        third='location' if s.label=='User' else 'viewCount' if s.label in ('Post','Question','Answer') else 'creationDate' if s.label=='Comment' else 'excerptPostId'
        if width>=3:query+=f', {s.endpoint}.{third} AS extra_field'
        cols=[column]
        if width>=2:cols.append('measurement AS '+s.sort_column)
        if width>=3:cols.append('extra_field AS '+{'location':'location','viewCount':'view_count','creationDate':'created_on','excerptPostId':'excerpt_post_id'}[third])
        return query+' RETURN '+', '.join(cols)
    def intent(self):
        return {'lookup':'List requested names, text or measurements of qualifying site entities.','projection':'List distinct displayed names or text of qualifying site entities.','count':'How many qualifying site entities are there?','group':'How many posts did each selected user author?','rank':'Which qualifying entity has the highest or lowest measurement?','ratio':'What percentage of qualifying posts have positive scores?'}[self.style]

def features(i,structure):
    sig=json.loads(structure['signature']);mode=structure['mode'];style=structure.get('v4_style')
    agg=sig['aggregation'][0]
    if mode=='ratio':agg='more than one aggregate' # SUM and COUNT in the expression.
    ordering={'argmax':'top 1','argmin':'top 1','order-by':'order with no limit','none':'none','top-k':'top-k','n-th ranked':'n-th ranked'}[sig['ordering']]
    extras=[]
    for key,name in [('DISTINCT projection','distinct projection'),('ratio/percentage','ratio'),('conditional aggregate','conditional aggregate'),('negation','negation'),('comparison between two named entities','comparison of two named entities'),('HAVING-style post-filter','having'),('existence','existence')]:
        if key in sig['extras']:extras.append(name)
    if not extras:extras=['none']
    width=len(i['rows'][0])
    return {'aggregation':agg,'ordering':ordering,'grouping':'yes' if sig['grouping']!='none' else 'no','extras':extras,'columns':'one' if width==1 else 'two' if width==2 else 'three or more','depth':'0-1' if i['hops']<=1 else '2' if i['hops']==2 else '3-4'}

def mix(rows,ss):
    counts={k:Counter() for k in TARGETS}
    for i in rows:
        f=features(i,ss[i['structure_id']])
        for k,v in f.items():counts[k].update(v if isinstance(v,list) else [v])
    return {k:{name:{'count':counts[k][name],'achieved_percent':100*counts[k][name]/max(1,len(rows)),'target_percent':target,'delta_points':100*counts[k][name]/max(1,len(rows))-target} for name,target in values.items()} for k,values in TARGETS.items()}

def plan():
    V4.mkdir(exist_ok=True)
    if not (V4/'frozen_manifest.json').exists():(V4/'frozen_manifest.json').write_text(json.dumps(frozen(),indent=2)+'\n')
    assert_frozen();ss,ii=load();known={s['structure_id']:s for s in ss}
    qs=[json.loads(l) for l in (OUT/'questions.jsonl').read_text().splitlines()];byid={i['instance_id']:i for i in ii}
    written=[byid[q['instance_id']] for q in qs if byid[q['instance_id']]['split']=='train']
    data={'current_written_training_questions':len(written),'current_mix':mix(written,known),'available_training_instances':sum(i['split']=='train' for i in ii),'held_component_count':len(forbidden(ss)),
          'decisions':['Add unordered single-column lookups, unordered distinct projections, plain entity counts and grouped authored-post counts; render ranking answers as a single meaningful column where needed.','Count means COUNT of entities without DISTINCT; reject samples where matching multiplicity would change the count. Existing explicit distinct-count families retain their classification.','Ratios use SUM and COUNT and are classified as more than one aggregate; conditional SUM(CASE ... THEN 1 ...) is classified by its intended count meaning, consistent with the frozen signature.','Return width is not part of the existing signature tuple, so meaningful projection changes may reuse a training structure signature with new v4 instance ids.','Negation is explicitly entirely held out and cannot be introduced; its achieved share must be zero.','Targets are approximate marginals, not an exclusive partition: their stated aggregation percentages do not sum to exactly a whole, and extras can overlap. Ordering under-one-percent / at-most-one-percent are enforced as upper bounds, not exact zero targets.']}
    data['aggregation_target_sum']=sum(TARGETS['aggregation'].values());data['extras_target_sum']=sum(TARGETS['extras'].values())
    (V4/'plan.json').write_text(json.dumps(data,indent=2)+'\n');checkpoint('step 1 complete',json.dumps(data,indent=2)+'\n\nNext: execute candidate additions. Existing outputs are frozen; all new outputs are confined to out/v4.');print(json.dumps(data,indent=2))

def candidates(ss):
    held={s['signature'] for s in ss if s['split']=='heldout_structure'};blocked=forbidden(ss);result={}
    for path in paths():
        if path.hops>2:continue
        root=path.labels[0]
        anchors=['id','date']+(['name'] if root in ('User','Tag') else ['title'] if root in ('Post','Question') else [])
        if root in ('User','Post','Question','Answer'):anchors.append('range')
        if root=='Tag':anchors=['name','range'] if not path.hops else ['name']
        for anchor in anchors:
            for style in ('lookup','projection','count','ratio','group'):
                if style=='count' and path.hops>1:continue
                if style=='ratio' and path.labels[-1] not in ('Post','Question','Answer'):continue
                if style=='group' and not(path.labels==('User','Post')):continue
                mode='ratio' if style=='ratio' else 'detail'
                v=Variant(Structure(path,mode,anchor),style)
                if v.signature in held or components(v)&blocked:continue
                result.setdefault(v.signature,v)
                if style=='group':
                    for filtered_mode in ('null','not_null'):
                        filtered=Variant(Structure(path,filtered_mode,anchor),style)
                        if filtered.signature not in held and not components(filtered)&blocked:result.setdefault(filtered.signature,filtered)
    # Single-column top-one variants reuse the signature whenever it is in training.
    from .structures import enumerate_structures
    training={s['signature'] for s in ss if s['split']=='train'}
    for s in enumerate_structures():
        if s.mode in ('argmax','bottom') and s.signature in training:
            v=Variant(s,'rank');result.setdefault(v.signature,v)
    return list(result.values())

def generate():
    assert_frozen();ss,ii=load();old={s['signature']:s for s in ss};blocked=forbidden(ss)
    logging.basicConfig(level=logging.INFO);handler=logging.FileHandler(V4/'debug.log');LOGGER.addHandler(handler);LOGGER.setLevel(logging.DEBUG);LOGGER.propagate=False
    config=dotenv_values(REPO/'.env');records=[];structs={s['structure_id']:s for s in ss if s['split']=='train'};rejects=Counter();details=[]
    with GraphDatabase.driver(str(config['BIRD_NEO4J_URI']),auth=(str(config['BIRD_NEO4J_USER']),str(config['BIRD_NEO4J_PASSWORD']))) as driver:
        graph=ReadGraph(driver);names={r['anchor']:str(r['name']) for r in graph.names()};pools={}
        catalog=candidates(ss)
        for index,v in enumerate(catalog):
            s=v.base;key=s.path.pattern
            if key not in pools:
                pool=graph.root_pool(s.path);random.Random(stable_seed(SEED,key)).shuffle(pool);pools[key]=pool[:240]
            params_list=parameter_sets(s,pools[key],names,SEED,36)
            if s.anchor=='range' and v.style in ('lookup','projection'):
                params_list=[dict(p,upper=p['lower']) for p in params_list]
            accepted=[];answers=set();used=set();local=Counter()
            for params in params_list:
                token=json.dumps(params,sort_keys=True)
                if token in used:continue
                used.add(token)
                width=3 if len(accepted)%6==0 and v.style in ('lookup','group') and s.label!='Tag' else 2 if len(accepted)%3==0 and v.style in ('lookup','group') else 1
                query=v.render(width)
                try:
                    if v.style in ('count','group'):
                        prefix=s.render().split('WITH DISTINCT')[0]
                        test=prefix+f'RETURN count({s.endpoint}) AS matches,count(DISTINCT {s.endpoint}) AS entities' if v.style=='count' else prefix+'WITH n0 AS person,count(n1) AS matches,count(DISTINCT n1) AS entities RETURN max(matches-entities) AS excess'
                        check,_=graph.execute(test,params)
                        if (check[0]['matches']!=check[0]['entities'] if v.style=='count' else check[0]['excess']!=0):local['multiplicity']+=1;continue
                    rows,runtime=graph.execute(query,params)
                    reason=rejection(rows,runtime)
                    if reason:local[reason]+=1;continue
                    if width>=3 and all(list(row.values())[-1] is None for row in rows):local['all_null_extra_column']+=1;continue
                    if v.style=='rank':
                        probe,_=graph.execute(s.render(probe=True),dict(params,probe_k=2))
                        if len(probe)>1 and probe[0][s.sort_column]==probe[1][s.sort_column]:local['cut_boundary_tie']+=1;continue
                    again,_=graph.execute(query,params)
                    if canonical_rows(rows)!=canonical_rows(again):local['unstable_result']+=1;continue
                    iid='v4_'+hashlib.sha256((v.signature+query+token).encode()).hexdigest()[:20]
                    accepted.append({'instance_id':iid,'structure_id':v.structure_id,'split':'train','hops':s.path.hops,'cypher':query,'params':params,'n_rows':len(rows),'rows':rows,'runtime_ms':round(runtime,3),'v4_style':v.style,'return_width':len(rows[0]),'base_mode':s.mode})
                    answers.add(canonical_rows(rows))
                    if len(accepted)==12:break
                except Neo4jError as error:local['execution_error:'+str(error.code)]+=1
            if len(answers)<2:local['trivial_constant_answer']+=len(accepted);accepted=[]
            if len(accepted)<6:local['fewer_than_6']+=len(accepted);accepted=[]
            rejects.update(local);details.append({'structure_id':v.structure_id,'style':v.style,'accepted':len(accepted),'rejections':dict(local)})
            if accepted:
                existing=old.get(v.signature)
                sid=existing['structure_id'] if existing else v.structure_id
                for i in accepted:i['structure_id']=sid
                structs[sid]=dict(existing) if existing else {'structure_id':sid,'signature':v.signature,'split':'train','novelty':None,'hops':s.path.hops,'mode':s.mode,'anchor_kind':s.anchor,'intent':v.intent(),'unseen_components':[]}
                structs[sid]['v4_style']=v.style;structs[sid]['base_path_labels']=s.path.labels;structs[sid]['base_path_edges']=s.path.edges
                records.extend(accepted)
            if (index+1)%10==0:print(json.dumps({'candidates_executed':index+1,'of':len(catalog),'new_pool_instances':len(records)}),flush=True)
    # Preserve frozen reused instances exactly; attach only separate shape metadata.
    pool=[dict(i) for i in ii if i['split']=='train']+records
    write_jsonl(V4/'pool.jsonl',pool);write_jsonl(V4/'pool_structures.jsonl',list(structs.values()))
    summary={'candidate_structures':len(catalog),'new_instances_accepted':len(records),'new_signatures_accepted':sum(sid not in {s['structure_id'] for s in ss} for sid in {i['structure_id'] for i in records}),'rejections':dict(rejects),'per_structure':details}
    (V4/'generation_report.json').write_text(json.dumps(summary,indent=2)+'\n');assert_frozen();checkpoint('step 2 complete',json.dumps({k:v for k,v in summary.items() if k!='per_structure'},indent=2)+'\n\nAll new instances were executed twice and matched. Count candidates additionally checked COUNT equals COUNT DISTINCT to reject multiplicity. Next: select the fixed-size mix.');print(json.dumps({k:v for k,v in summary.items() if k!='per_structure'},indent=2))


def select():
    assert_frozen();ss,_=load();pool=[json.loads(l) for l in (V4/'pool.jsonl').read_text().splitlines()];structs={s['structure_id']:s for s in [json.loads(l) for l in (V4/'pool_structures.jsonl').read_text().splitlines()]}
    # Existing ids need their original shape even when a new projection shares their signature.
    old={s['structure_id']:s for s in ss};fs=[features(i,structs[i['structure_id']] if i['instance_id'].startswith('v4_') else old[i['structure_id']]) for i in pool]
    axes=[(k,name) for k,values in TARGETS.items() for name in values]
    vectors=[[int(name in f[k]) if isinstance(f[k],list) else int(name==f[k]) for k,name in axes] for f in fs]
    targets=[TARGETS[k][name]*320/100 for k,name in axes]
    # Exact aggregation quotas chosen from stated marginal targets; ratio is multi-aggregate.
    quotas={'none':176,'count':80,'sum':19,'count distinct':9,'avg':5,'max':4,'min':3,'more than one aggregate':24}
    assert sum(quotas.values())==320
    rng=random.Random(SEED);groups=defaultdict(list)
    for index,f in enumerate(fs):groups[f['aggregation']].append(index)
    selected=set();per=Counter();counts=[0]*len(axes)
    def loss(values):
        score=0
        for j,(k,name) in enumerate(axes):
            delta=values[j]-targets[j]
            if k=='ordering' and name in ('n-th ranked','order with no limit'):delta=max(0,values[j]-3)
            # Negation is forbidden; its unavoidable shortfall is fixed.
            if k=='extras' and name=='negation':continue
            excess=max(0,abs(delta)-8)
            score+=delta*delta+100*excess*excess
            if k=='ordering' and name in ('n-th ranked','order with no limit'):score+=100000*max(0,values[j]-3)**2
            if k=='extras' and name=='distinct projection':score+=100000*max(0,values[j]-28)**2
        return score
    for agg,amount in quotas.items():
        candidates=groups[agg][:];rng.shuffle(candidates)
        for unused in range(amount):
            available=[j for j in candidates if j not in selected and per[pool[j]['structure_id']]<5]
            if not available:raise ValueError('Insufficient eligible '+agg+' capacity')
            j=min(available,key=lambda j:loss([a+b for a,b in zip(counts,vectors[j])]))
            selected.add(j);per[pool[j]['structure_id']]+=1;counts=[a+b for a,b in zip(counts,vectors[j])]
    best=loss(counts)
    # Seeded same-aggregate swaps retain every exact quota and the structure cap.
    for iteration in range(120000):
        before=rng.choice(tuple(selected));after=rng.choice(groups[fs[before]['aggregation']])
        if after in selected:continue
        a,b=pool[before]['structure_id'],pool[after]['structure_id']
        if a!=b and per[b]>=5:continue
        candidate=[n-x+y for n,x,y in zip(counts,vectors[before],vectors[after])];cost=loss(candidate)
        if cost<best or cost==best and rng.random()<.02:
            selected.remove(before);selected.add(after);per[a]-=1;per[b]+=1;counts=candidate;best=cost
    chosen=[pool[j] for j in sorted(selected,key=lambda j:(fs[j]['depth'],pool[j]['structure_id'],pool[j]['instance_id']))]
    selected_structures={i['structure_id']:structs[i['structure_id']] for i in chosen}
    # Store instance-level classification because column projection is intentionally not a signature field.
    for i in chosen:
        j=next(j for j in selected if pool[j]['instance_id']==i['instance_id']);i['shape']=fs[j]
        s=selected_structures[i['structure_id']]
        basic=Structure(Path(tuple(s['base_path_labels']),tuple(tuple(e) for e in s['base_path_edges'])),s['mode'],s.get('anchor_kind','id')) if s.get('base_path_labels') else None
        if basic and i['instance_id'].startswith('v4_'):
            value=hint(basic,i['instance_id'])
            if value:
                style=i['v4_style']
                if style in ('count','group','projection'):
                    mapping={'score':('score','Score'),'reputation':('reputation','Reputation'),'count':('stored tag usage count','Count'),'displayName':('display name','DisplayName'),'tagName':('tag name','TagName'),'title':('title','Title'),'body':('body','Body'),'text':('comment text','Text'),'creationDate':('creation date','CreationDate'),'closedDate':('closing date','ClosedDate'),'lastEditDate':('last edit date','LastEditDate'),'location':('location','Location'),'userId':('user ID','Id'),'postId':('post ID','Id'),'commentId':('comment ID','Id')}
                    fields=set(re.findall(r'\.([A-Za-z][A-Za-z0-9]*)',i['cypher']))
                    parts=[phrase+' refers to '+source for field,(phrase,source) in mapping.items() if field in fields]
                    if 'creationDate' in fields:
                        for match in re.finditer(r'n(\d+)\.creationDate',i['cypher']):
                            if basic.path.labels[int(match.group(1))] in ('Post','Question','Answer'):parts.append('post creation date refers to CreaionDate')
                    if style=='count':parts.append('the count refers to qualifying entities, each counted once')
                    if style=='group':parts.append('the post count refers to posts per selected author; users without matching posts are absent')
                    if style=='projection':parts.append('the list refers to distinct displayed names or text, without ordering')
                    if 'left(' in i['cypher']:parts.append('the preview refers to the first 120 characters')
                    value='; '.join(parts)+'.'
                i['hint']=value
            else:i.pop('hint',None)
        # Frozen reused hints already live on copied instances.
    held={s['signature'] for s in ss if s['split']=='heldout_structure'};blocked=forbidden(ss)
    class Sig:
        def __init__(self,signature):self.signature=signature
    violations=[sid for sid,s in selected_structures.items() if s['signature'] in held];introduced={c for s in selected_structures.values() for c in components(Sig(s['signature']))}&blocked
    assert not violations and not introduced
    old_sids={s['structure_id'] for s in ss}
    # Shares use instance shapes, not signature-derived aggregate aliases.
    actual={k:Counter() for k in TARGETS}
    for i in chosen:
        for k,v in i['shape'].items():actual[k].update(v if isinstance(v,list) else [v])
    achieved={k:{name:{'count':actual[k][name],'achieved_percent':100*actual[k][name]/len(chosen),'target_percent':target,'delta_points':100*actual[k][name]/len(chosen)-target,'target_rule':('<1%' if name=='n-th ranked' else '<=1%' if name=='order with no limit' else '<=9%' if name=='distinct projection' else 'about target, within three percentage points'),'within_tolerance':abs(100*actual[k][name]/len(chosen)-target)<=3.000001 if not(k=='ordering' and name in ('n-th ranked','order with no limit')) else 100*actual[k][name]/len(chosen)<1} for name,target in values.items()} for k,values in TARGETS.items()}
    report={'status':'step 3 complete; individual wording pending','selected_instances':len(chosen),'questions_written':0,'how_many_combined':{'count':actual['aggregation']['count']+actual['aggregation']['count distinct'],'achieved_percent':100*(actual['aggregation']['count']+actual['aggregation']['count distinct'])/len(chosen),'target_percent':28},'distinct_projection_ceiling_pass':100*actual['extras']['distinct projection']/len(chosen)<=9,'depth_departure':'The deeper-hop target is deliberately above the human distribution, as stated in amendment D notes.','mix':achieved,'structure_counts':{'reused':sum(sid in old_sids for sid in selected_structures),'new':sum(sid not in old_sids for sid in selected_structures)},'instance_counts':{'reused':sum(not i['instance_id'].startswith('v4_') for i in chosen),'new':sum(i['instance_id'].startswith('v4_') for i in chosen)},'max_questions_per_structure_planned':max(per.values()),'heldout_checks':{'no_heldout_signature':not violations,'no_heldout_component_introduced':not introduced,'signature_collisions':violations,'introduced_components':sorted(introduced)},'frozen_files_unchanged':True,'hints':{'with_hint':sum('hint' in i for i in chosen),'share':sum('hint' in i for i in chosen)/len(chosen)},'interpretations':json.loads((V4/'plan.json').read_text())['decisions']}
    (V4/'new_structures.json').write_text(json.dumps([{'structure_id':sid,'signature':s['signature']} for sid,s in selected_structures.items() if sid not in old_sids],indent=2)+'\n');write_jsonl(V4/'instances_v4_train.jsonl',chosen);write_jsonl(V4/'structures_v4_train.jsonl',list(selected_structures.values()));(V4/'report.json').write_text(json.dumps(report,indent=2)+'\n');assert_frozen();checkpoint('step 3 complete',json.dumps(report,indent=2)+'\n\nNext: write each selected question individually; no v4 questions are yet ready for training.');print(json.dumps(report,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('step',choices=['plan','generate','select']);args=p.parse_args();globals()[args.step]()
