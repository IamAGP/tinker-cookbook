"""Deterministic hints from query parts; no teacher or evaluation input."""
from __future__ import annotations
import hashlib
from .structures import Structure, PROPERTIES

SOURCE_FIELDS = {'score':'Score','reputation':'Reputation','count':'Count','viewCount':'ViewCount',
                 'displayName':'DisplayName','title':'Title','location':'Location',
                 'closedDate':'ClosedDate','lastEditDate':'LastEditDate','userDisplayName':'UserDisplayName',
                 'tagName':'TagName','name':'Name','userId':'Id','postId':'Id','commentId':'Id'}


def hint(structure: Structure, instance_id: str) -> str | None:
    # Deterministic Bernoulli-style assignment, threshold exactly 92/100.
    if int.from_bytes(hashlib.sha256(('hint:'+instance_id).encode()).digest()[:8],'big') % 100 >= 92:
        return None
    metric=structure.metric
    phrase={'score':'score','reputation':'reputation','count':'stored tag usage count','viewCount':'view count'}.get(metric,metric)
    parts=[f'{phrase} refers to {SOURCE_FIELDS.get(metric,metric)}']
    if structure.label=='User': parts.append('display name refers to DisplayName')
    elif structure.label=='Tag': parts.append('tag name refers to TagName')
    elif structure.label=='Comment': parts.append('comment preview refers to the first 120 characters of Text')
    elif structure.label=='Answer': parts.append('answer preview refers to the first 120 characters of Body')
    else: parts.append('post text refers to Title when present, otherwise the first 120 characters of Body')
    if structure.anchor=='name':
        field='DisplayName' if structure.path.labels[0]=='User' else 'TagName'
        parts.append(f'the selected name refers to {field}')
    if structure.anchor=='title': parts.append('the selected title refers to Title')
    if structure.anchor=='badge': parts.append('the badge name refers to Name')
    if structure.anchor=='date': parts.append('the date refers to the calendar day in '+('CreaionDate' if structure.path.labels[0] in ('Post','Question','Answer') else 'CreationDate'))
    if structure.mode=='year': parts.append('the year interval refers to the year of '+('CreaionDate' if structure.label in ('Post','Question','Answer') else 'CreationDate')+', including both endpoints')
    if structure.mode in ('null','not_null'):
        field=PROPERTIES[structure.label][2]
        parts.append(f'the missing-value condition refers to {SOURCE_FIELDS.get(field,field)} being '+('absent' if structure.mode=='null' else 'present'))
    if structure.mode in ('contains','starts'):
        field='DisplayName' if structure.label=='User' else 'TagName' if structure.label=='Tag' else 'Title'
        parts.append(f'the text condition refers to a case-sensitive '+('substring' if structure.mode=='contains' else 'prefix')+f' of {field}')
    if structure.mode=='ratio': parts.append('the percentage refers to 100 times the number of distinct qualifying entities with a positive stored measurement divided by all distinct qualifying entities, including missing measurements')
    if structure.mode=='comparison': parts.append('the difference refers to the first named user total minus the second named user total, counting each qualifying entity once per user')
    if structure.mode=='nth': parts.append('the rank refers to descending stored measurement, starting at one')
    if structure.mode=='projection': parts.append('the list refers to distinct displayed names or text, sorted alphabetically')
    if structure.mode in ('conditional_count','conditional_sum'): parts.append('the condition refers to a stored measurement greater than or equal to the stated threshold; nonqualifying or missing measurements contribute zero')
    if structure.mode in ('entity_group','entity_having'): parts.append('the associated count refers to distinct associated entities, not repeated matches')
    parts.append('each qualifying entity is counted once')
    return '; '.join(parts)+'.'


def main() -> None:
    import json
    from collections import Counter
    from .generate import HERE, write_jsonl
    from .structures import enumerate_structures
    out=HERE/'out'
    known={s.structure_id:s for s in enumerate_structures()}
    instances=[json.loads(line) for line in (out/'instances.jsonl').read_text().splitlines()]
    n=0
    for instance in instances:
        value=hint(known[instance['structure_id']],instance['instance_id'])
        if value is not None:
            instance['hint']=value
            n+=1
        else:
            instance.pop('hint',None)
    write_jsonl(out/'instances.jsonl',instances)
    report=json.loads((out/'report.json').read_text())
    report['hints']={'with_hint':n,'without_hint':len(instances)-n,'share':n/len(instances),
                     'source_mapping':'Posts.CreaionDate verified in etl/lambda_export.py; other creation dates CreationDate'}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report['hints']))


if __name__=='__main__':
    main()
