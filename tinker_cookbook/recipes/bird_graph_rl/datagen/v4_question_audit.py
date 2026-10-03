"""Audit coverage, frozen inputs and held-out question overlap without evaluation data."""
from __future__ import annotations
from collections import Counter,defaultdict
import hashlib,json,re
from .v4 import V4,OUT,HERE,assert_frozen
from .v4_question_authoring import INSTANCE_SHA,QUEUE,d,structure


def normalize(text):return re.sub(r'\s+',' ',text).strip().casefold()

def main():
    assert_frozen()
    instances=[json.loads(line) for line in (V4/'instances_v4_train.jsonl').read_text().splitlines()]
    questions=[json.loads(line) for line in (V4/'questions_v4_train.jsonl').read_text().splitlines()]
    held_ids={i['instance_id'] for i in [json.loads(line) for line in (OUT/'instances.jsonl').read_text().splitlines()] if i['split']!='train'}
    held=[q for q in [json.loads(line) for line in (OUT/'questions.jsonl').read_text().splitlines()] if q['instance_id'] in held_ids]
    held_text={q['question'] for q in held};held_normalized={normalize(q) for q in held_text}
    byid={q['instance_id']:q['question'] for q in questions};iid={i['instance_id'] for i in instances}
    aliases=[];vocabulary=[];frames=defaultdict(list)
    for index,item in enumerate(QUEUE):
        sentence=byid[item['instance_id']]
        checked=sentence.replace(d(index),'__SUBJECT__')
        for literal in item['params'].values():
            if isinstance(literal,str):checked=checked.replace(repr(literal),'__LITERAL__')
        if re.search(r'\b(?:value|entity_id|post_text|user_name|associated_count|positive_percentage|extra_field|identity)\b',checked):aliases.append(item['instance_id'])
        if re.search(r'\b(?:member|standing points|node|edge|relationship|route|connection|path)\b',checked,re.I):vocabulary.append(item['instance_id'])
        for literal in item['params'].values():checked=checked.replace(str(literal),'__PARAM__')
        frames[(item['structure_id'],normalize(checked))].append(item['instance_id'])
    checks={'selected_instances':len(instances),'questions_written':len(questions),'unique_instance_ids':len(byid),'complete_coverage':set(byid)==iid,'heldout_questions_checked':len(held),'heldout_exact_overlaps':[q['instance_id'] for q in questions if q['question'] in held_text],'heldout_normalized_overlaps':[q['instance_id'] for q in questions if normalize(q['question']) in held_normalized],'duplicate_questions':len(questions)-len({q['question'] for q in questions}),'alias_mentions':aliases,'prohibited_vocabulary':vocabulary,'identical_subject_normalized_frames_within_structure':[values for values in frames.values() if len(values)>1],'max_questions_per_structure':max(Counter(i['structure_id'] for i in instances).values()),'selected_instances_unchanged':hashlib.sha256((V4/'instances_v4_train.jsonl').read_bytes()).hexdigest()==INSTANCE_SHA}
    assert checks['complete_coverage'] and checks['selected_instances_unchanged']
    assert not checks['heldout_exact_overlaps'] and not checks['heldout_normalized_overlaps'] and not checks['duplicate_questions'] and not aliases and not vocabulary
    (V4/'question_audit.json').write_text(json.dumps(checks,indent=2)+'\n')
    report=json.loads((V4/'report.json').read_text())
    report.update(status='first v4 batch complete: questions individually authored and audited',questions_written=len(questions),question_checks=checks,heldout_question_overlap_check='passed: exact and case/whitespace-normalized overlap checks',next_step='Amendment D2: select and verify disjoint additional instances, enforcing the combined structure cap, then author their questions.')
    (V4/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    summary='\n## First v4 question set complete\n\n'+json.dumps(checks,indent=2)+'\n\nQuestions were individually composed in the numbered v4 batch modules and polished after reading the rendered text. Literal and subject helpers bind data; no question-generation templates were used. Hints and selected instances were not changed. Frame checks are a mechanical screen, not an independent human naturalness review.\n'
    for file in (V4/'CHECKPOINT.md',HERE/'README.md'):
        with file.open('a') as stream:stream.write(summary)
    assert_frozen();print(json.dumps(checks,indent=2))


if __name__=='__main__':main()
