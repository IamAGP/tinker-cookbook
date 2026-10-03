"""Apply only authorized review corrections; retain all other JSONL lines verbatim."""
from __future__ import annotations
from collections import Counter
import hashlib,json,re
from pathlib import Path
from dotenv import dotenv_values
from neo4j import GraphDatabase
from .generate import ReadGraph,REPO,canonical_rows,rejection,HERE
from .structures import components
from .v4 import V4,load,forbidden,assert_frozen


def parameter_echo(item):
    """Reject a single scalar answer identical to any parameter, including numbers."""
    rows=item['rows']
    return len(rows)==1 and len(rows[0])==1 and next(iter(rows[0].values())) in item['params'].values()


def checkpoint(title,value):
    for file in (V4/'CHECKPOINT.md',HERE/'README.md'):
        with file.open('a') as out:out.write('\n## '+title+'\n\n'+json.dumps(value,indent=2)+'\n')


def apply(batch):
    assert_frozen()
    suffix='' if batch=='batch1' else '_batch2'
    ip=V4/('instances_v4_train'+suffix+'.jsonl');qp=V4/('questions_v4_train'+suffix+'.jsonl')
    sp=V4/('structures_v4_train'+suffix+'.jsonl')
    findings=json.loads((V4/'review_findings.json').read_text())[batch]
    originals=ip.read_text().splitlines(keepends=True);qoriginals=qp.read_text().splitlines(keepends=True)
    snapshot=V4/('before_review_'+batch);snapshot.mkdir(exist_ok=True)
    for file in (ip,qp,sp):
        target=snapshot/file.name
        if not target.exists():target.write_bytes(file.read_bytes())
    rows={json.loads(line)['instance_id']:json.loads(line) for line in originals}
    structs={s['structure_id']:s for s in [json.loads(line) for line in sp.read_text().splitlines()]}
    old,_=load();held={s['signature'] for s in old if s['split']=='heldout_structure'};blocked=forbidden(old)
    class Signature:
        def __init__(self,text):self.signature=text
    replacements={};inspection=[];questions={};rejects=Counter()
    config=dotenv_values(REPO/'.env')
    with GraphDatabase.driver(str(config['BIRD_NEO4J_URI']),auth=(str(config['BIRD_NEO4J_USER']),str(config['BIRD_NEO4J_PASSWORD']))) as driver:
        graph=ReadGraph(driver)
        for index,iid in enumerate(findings['answer_stated_in_question']):
            item=rows[iid];s=structs[item['structure_id']]
            assert s['signature'] not in held and not components(Signature(s['signature']))&blocked
            label=s['base_path_labels'][0]
            fields=['reputation','creationDate','location'] if label=='User' else ['count'] if label=='Tag' else ['score','viewCount','creationDate']
            # Vary meaningful attributes within each structure. Runtime evidence chooses the first usable one.
            rotation=index%len(fields);fields=fields[rotation:]+fields[:rotation]
            for field in fields:
                expression='n0.'+field
                prefix=item['cypher'].split('WITH DISTINCT')[0].split('RETURN DISTINCT')[0]
                distinct='DISTINCT ' if item['shape']['extras']==['distinct projection'] else ''
                query=prefix+'RETURN '+distinct+expression+' AS '+{'creationDate':'created_on','count':'stored_tag_count'}.get(field,field)
                result,runtime=graph.execute(query,item['params']);reason=rejection(result,runtime)
                if reason:rejects[reason]+=1;continue
                replacement=dict(item,cypher=query,rows=result,n_rows=len(result),runtime_ms=runtime,v4_output_attribute=field)
                if parameter_echo(replacement):rejects['parameter_echo']+=1;continue
                again,_=graph.execute(query,item['params'])
                if canonical_rows(result)!=canonical_rows(again):rejects['unstable']+=1;continue
                replacement['instance_id']='v4_'+hashlib.sha256((s['signature']+query+json.dumps(item['params'],sort_keys=True)).encode()).hexdigest()[:20]
                assert replacement['shape']==item['shape'] and replacement['hops']==item['hops']
                if 'hint' in item:
                    phrase,source={'reputation':('reputation','Reputation'),'creationDate':('creation date','CreationDate' if label=='User' else 'CreaionDate'),'location':('location','Location'),'count':('stored tag usage count','Count'),'score':('score','Score'),'viewCount':('view count','ViewCount')}[field]
                    replacement['hint']=phrase+' refers to '+source+'; '+('the selected name refers to DisplayName' if label=='User' else 'the tag name refers to TagName' if label=='Tag' else 'the selected title refers to Title')+'.'
                replacements[iid]=replacement;inspection.append({'old_id':iid,'new_id':replacement['instance_id'],'attribute':field,'rows':result,'repeat_matches':True,'signature_guard':True,'component_guard':True,'shape_preserved':True})
                break
            else:raise ValueError('No usable non-echo attribute for '+iid)
    # Each question below is individually written for its specific replacement.
    for index,iid in enumerate(findings['answer_stated_in_question']):
        item=replacements[iid];field=item['v4_output_attribute'];label=structs[item['structure_id']]['base_path_labels'][0];param=repr(item['params'].get('name',item['params'].get('title')))
        phrase={'reputation':'reputation','creationDate':'creation date and time','location':'recorded location','count':'stored tag usage count','score':'score','viewCount':'view count'}[field]
        questions[iid]=(item,phrase,param,label)
    # Return the metadata for explicit authoring; never generate question sentences here.
    (V4/('review_replacements_'+batch+'.json')).write_text(json.dumps({'replacements':replacements,'inspection':inspection,'rejections':dict(rejects)},indent=2)+'\n')
    print(json.dumps({'batch':batch,'replacements_verified':len(replacements),'rejections':dict(rejects),'authoring':[{'old_id':iid,'new_id':item['instance_id'],'field':phrase,'param':param,'label':label} for iid,(item,phrase,param,label) in questions.items()]},indent=2))


if __name__=='__main__':
    import sys
    apply(sys.argv[1])


def install(batch):
    from .v4_review_questions import questions
    suffix='' if batch=='batch1' else '_batch2';ip=V4/('instances_v4_train'+suffix+'.jsonl');qp=V4/('questions_v4_train'+suffix+'.jsonl')
    data=json.loads((V4/('review_replacements_'+batch+'.json')).read_text());replacements=data['replacements'];authored=questions(batch)
    before_i=ip.read_text().splitlines(keepends=True);before_q=qp.read_text().splitlines(keepends=True)
    after_i=[json.dumps(replacements[json.loads(line)['instance_id']],ensure_ascii=False)+'\n' if json.loads(line)['instance_id'] in replacements else line for line in before_i]
    after_q=[json.dumps({'instance_id':replacements[json.loads(line)['instance_id']]['instance_id'],'question':authored[json.loads(line)['instance_id']]},ensure_ascii=False)+'\n' if json.loads(line)['instance_id'] in replacements else line for line in before_q]
    assert all(a==b for a,b in zip(before_i,after_i) if json.loads(a)['instance_id'] not in replacements)
    assert all(a==b for a,b in zip(before_q,after_q) if json.loads(a)['instance_id'] not in replacements)
    ip.write_text(''.join(after_i));qp.write_text(''.join(after_q))
    # Store separately written questions for replacements not yet reached in the authoring queue.
    pending=[{'instance_id':replacements[iid]['instance_id'],'question':sentence} for iid,sentence in authored.items() if iid not in {json.loads(line)['instance_id'] for line in before_q}]
    (V4/('review_pending_questions_'+batch+'.json')).write_text(json.dumps(pending,indent=2,ensure_ascii=False)+'\n')
    summary={'batch':batch,'lookups_replaced':len(replacements),'questions_replaced':sum(json.loads(line)['instance_id'] in replacements for line in before_q),'replacement_questions_pre_authored_for_pending_queue':len(pending),'untouched_instance_lines':sum(json.loads(line)['instance_id'] not in replacements for line in before_i),'untouched_question_lines':sum(json.loads(line)['instance_id'] not in replacements for line in before_q),'mix_cells_preserved':all(replacements[json.loads(line)['instance_id']]['shape']==json.loads(line)['shape'] for line in before_i if json.loads(line)['instance_id'] in replacements),'rejections':data['rejections']}
    checkpoint('Review step 1 replacement installation '+batch,summary);print(json.dumps(summary))


def fix_ranges(batch):
    suffix='' if batch=='batch1' else '_batch2';ip=V4/('instances_v4_train'+suffix+'.jsonl');qp=V4/('questions_v4_train'+suffix+'.jsonl')
    rows={i['instance_id']:i for i in [json.loads(line) for line in ip.read_text().splitlines()]}
    selected=set(json.loads((V4/'review_findings.json').read_text())[batch]['range_with_equal_bounds'])
    before=qp.read_text().splitlines(keepends=True);after=[];changed=[]
    for line in before:
        q=json.loads(line);item=rows[q['instance_id']]
        if q['instance_id'] in selected:
            assert item['params']['lower']==item['params']['upper']
            number=str(item['params']['lower']);text=q['question']
            revised=text.replace('between '+number+' and '+number+' inclusive','exactly '+number)
            if revised!=text:q['question']=revised;changed.append(q['instance_id']);line=json.dumps(q,ensure_ascii=False)+'\n'
        after.append(line)
    qp.write_text(''.join(after))
    summary={'batch':batch,'equal_bound_questions_reworded':len(changed),'review_equal_bound_instances':len(selected),'written_equal_bound_questions_already_natural':sum(json.loads(line)['instance_id'] in selected for line in before)-len(changed),'instance_file_unchanged_by_wording':True,'untouched_question_lines_preserved':all(a==b for a,b in zip(before,after) if json.loads(a)['instance_id'] not in changed)}
    checkpoint('Review step 2 equal-range wording '+batch,summary);print(json.dumps(summary))
