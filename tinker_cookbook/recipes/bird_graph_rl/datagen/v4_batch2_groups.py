"""Natural per-author comment counts to fill measured grouping capacity shortfall."""
from __future__ import annotations
from collections import Counter
import hashlib,json,random
from dotenv import dotenv_values
from neo4j import GraphDatabase
from .structures import Structure,paths,canonical_signature,components
from .generate import ReadGraph,REPO,parameter_sets,stable_seed,canonical_rows,rejection,write_jsonl
from .v4 import V4,load,forbidden,SEED,assert_frozen
from .v4_batch2 import checkpoint


def main():
    assert_frozen();old,_=load();held={s['signature'] for s in old if s['split']=='heldout_structure'};blocked=forbidden(old)
    path=paths()[5];records=[];structures=[];rejects=Counter()
    config=dotenv_values(REPO/'.env')
    with GraphDatabase.driver(str(config['BIRD_NEO4J_URI']),auth=(str(config['BIRD_NEO4J_USER']),str(config['BIRD_NEO4J_PASSWORD']))) as driver:
        graph=ReadGraph(driver);pool=graph.root_pool(path);random.Random(SEED+2).shuffle(pool);names={r['anchor']:r['name'] for r in graph.names()}
        for anchor in ('id','name','date','range'):
            base=Structure(path,'detail',anchor);sig=json.loads(base.signature)
            signature=canonical_signature(path,[tuple(pair) for pair in sig['filters']],('count','Comment'),'User','none',())
            class Signature:
                def __init__(self,value):self.signature=value
            assert signature not in held and not components(Signature(signature))&blocked
            sid='s_'+hashlib.sha256(signature.encode()).hexdigest()[:16]
            samples=[];answers=set()
            for params in parameter_sets(base,pool[:240],names,SEED+2,36):
                prefix=base.render().split('WITH DISTINCT')[0]
                probe=prefix+'WITH n0 AS person,count(n1) AS matches,count(DISTINCT n1) AS entities RETURN max(matches-entities) AS excess'
                proof,_=graph.execute(probe,params)
                if proof[0]['excess']!=0:rejects['multiplicity']+=1;continue
                width=3 if len(samples)%6==0 else 2 if len(samples)%3==0 else 1
                cols=['comment_count'] if width==1 else ['person.displayName AS user_name','comment_count']
                if width==3:cols.append('person.reputation AS reputation')
                query=prefix+'WITH n0 AS person,count(n1) AS comment_count RETURN '+', '.join(cols)
                rows,runtime=graph.execute(query,params);reason=rejection(rows,runtime)
                if reason:rejects[reason]+=1;continue
                again,_=graph.execute(query,params)
                if canonical_rows(rows)!=canonical_rows(again):rejects['unstable']+=1;continue
                token=json.dumps(params,sort_keys=True)
                iid='v4_'+hashlib.sha256((signature+query+token).encode()).hexdigest()[:20]
                samples.append({'instance_id':iid,'structure_id':sid,'split':'train','hops':1,'cypher':query,'params':params,'n_rows':len(rows),'rows':rows,'runtime_ms':runtime,'v4_style':'group_comment','return_width':width,'base_mode':'detail'})
                answers.add(canonical_rows(rows))
                if len(samples)==12:break
            if len(samples)<6 or len(answers)<2:rejects['insufficient_or_constant']+=len(samples);continue
            records.extend(samples);structures.append({'structure_id':sid,'signature':signature,'split':'train','novelty':None,'hops':1,'mode':'detail','anchor_kind':anchor,'intent':'How many comments did each selected user write?','unseen_components':[],'v4_style':'group_comment','base_path_labels':path.labels,'base_path_edges':path.edges})
    write_jsonl(V4/'extra_pool_batch2.jsonl',records);write_jsonl(V4/'extra_structures_batch2.jsonl',structures)
    summary={'natural_new_group_structures':len(structures),'new_verified_instances':len(records),'rejections':dict(rejects)}
    checkpoint('Second batch grouping additions verified',summary);print(json.dumps(summary))


if __name__=='__main__':main()
