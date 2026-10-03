"""Freeze a reproducible held-out question queue without changing any instances."""
from __future__ import annotations
import hashlib
import json
from collections import Counter,defaultdict
from .generate import HERE,write_jsonl

SEED='heldout-questions-20261003'

def ranked(instance):return hashlib.sha256((SEED+':'+instance['instance_id']).encode()).hexdigest()

def main():
    out=HERE/'out'
    instances=[json.loads(l) for l in (out/'instances.jsonl').read_text().splitlines()]
    structures={s['structure_id']:s for s in [json.loads(l) for l in (out/'structures.jsonl').read_text().splitlines()]}
    groups=defaultdict(list)
    for i in instances:groups[i['structure_id']].append(i)
    hi=defaultdict(list)
    for i in instances:
        if i['split']=='heldout_instance':hi[i['structure_id']].append(i)
    hi={sid:sorted(group,key=ranked) for sid,group in hi.items()}
    hi_queue=[group[j] for j in range(max(map(len,hi.values()))) for sid,group in sorted(hi.items()) if j<len(group)]
    nc=[]
    for sid,s in sorted(structures.items()):
        if s['novelty']!='novel_component':continue
        used=set();kept=[]
        for i in sorted(groups[sid],key=ranked):
            parameter=json.dumps(i['params'],sort_keys=True,ensure_ascii=False)
            if parameter not in used:kept.append(i);used.add(parameter)
            if len(kept)==4:break
        nc.extend(kept)
    combos=defaultdict(list)
    for sid,s in sorted(structures.items()):
        if s['novelty']=='novel_combination':combos[s['hops']].append(sorted(groups[sid],key=ranked)[0])
    candidates=[group[j] for j in range(max(map(len,combos.values()))) for hop,group in sorted(combos.items()) if j<len(group)]
    chosen=nc+candidates[:max(0,360-len(nc))]
    sample={'seed':SEED,'selection_rule':'For every novel_component structure in structure_id order, select up to four instances with distinct canonical full params, ranked by SHA256(seed + colon + instance_id). For novel_combination, take the top-ranked instance per structure; sort structures within hop by structure_id, then cycle ascending available hop counts until the total sample reaches 360. No answer or question content is used to rank instances.',
            'instance_ids':[i['instance_id'] for i in chosen],
            'counts_by_novelty':dict(Counter(structures[i['structure_id']]['novelty'] for i in chosen)),
            'counts_by_hop':dict(Counter(str(i['hops']) for i in chosen)),
            'counts_by_novelty_hop':{tag:{str(h):sum(structures[i['structure_id']]['novelty']==tag and i['hops']==h for i in chosen) for h in range(5)} for tag in ('novel_component','novel_combination')},
            'n_instances':len(chosen),'n_structures':len({i['structure_id'] for i in chosen})}
    (out/'heldout_structure_sample.json').write_text(json.dumps(sample,indent=2)+'\n')
    write_jsonl(out/'heldout_question_queue.jsonl',hi_queue+chosen)
    qbytes=(out/'questions.jsonl').read_bytes()
    frozen={'instances_sha256':hashlib.sha256((out/'instances.jsonl').read_bytes()).hexdigest(),'structures_sha256':hashlib.sha256((out/'structures.jsonl').read_bytes()).hexdigest(),'original_questions_bytes':len(qbytes),'original_questions_sha256':hashlib.sha256(qbytes).hexdigest(),'original_questions_count':len(qbytes.splitlines())}
    (out/'heldout_frozen.json').write_text(json.dumps(frozen,indent=2)+'\n')
    with (HERE/'README.md').open('a') as f:f.write('\n## Held-out selection checkpoint\n\nCurrent owner priority: stop training question writing; retain current ids and splits. Frozen hashes and original question prefix are in heldout_frozen.json. All held-out-instance instances appear first in heldout_question_queue.jsonl, round-robin by structure_id, with each structure’s instances sorted by the seeded hash. Measured held-out-instance count: '+str(len(hi_queue))+'. Then use the frozen heldout_structure_sample.json selection below.\n\n```json\n'+json.dumps({k:v for k,v in sample.items() if k!='instance_ids'},indent=2)+'\n```\n\nNext: append individually authored held-out-instance questions, then the selected held-out-structure questions; checkpoint after each batch.\n')
    print(json.dumps({'heldout_instance_queue':len(hi_queue),'heldout_structure_sample':{k:v for k,v in sample.items() if k not in ('instance_ids','selection_rule')}}))

if __name__=='__main__':main()
