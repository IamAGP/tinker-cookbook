"""Complete wording audit for the final reviewed first and second training batches."""
from __future__ import annotations
from collections import Counter,defaultdict
import hashlib,json,re
from .v4 import V4,HERE,OUT,assert_frozen
from .structures import Structure,Path,enumerate_structures
from .pilot import subject
from .v4_review_fix import checkpoint,parameter_echo


def main():
    assert_frozen()
    batches=[];old={s.structure_id:s for s in enumerate_structures()}
    legacy={i['instance_id']:i for i in [json.loads(line) for line in (OUT/'instances.jsonl').read_text().splitlines()]}
    held=[q for q in [json.loads(line) for line in (OUT/'questions.jsonl').read_text().splitlines()] if legacy[q['instance_id']]['split']!='train']
    norm=lambda text:re.sub(r'\s+',' ',text).strip().casefold()
    held_text={norm(q['question']) for q in held};frames=defaultdict(list);all_text=[];all_ids=[]
    for batch,suffix in [('batch1',''),('batch2','_batch2')]:
        rows=[json.loads(line) for line in (V4/('instances_v4_train'+suffix+'.jsonl')).read_text().splitlines()]
        questions=[json.loads(line) for line in (V4/('questions_v4_train'+suffix+'.jsonl')).read_text().splitlines()]
        ss={s['structure_id']:s for s in [json.loads(line) for line in (V4/('structures_v4_train'+suffix+'.jsonl')).read_text().splitlines()]}
        byid={q['instance_id']:q['question'] for q in questions};aliases=[];vocabulary=[];field_mismatches=[]
        for item in rows:
            sentence=byid[item['instance_id']];stored=ss[item['structure_id']]
            s=Structure(Path(tuple(stored['base_path_labels']),tuple(tuple(e) for e in stored['base_path_edges'])),item['base_mode'],stored.get('anchor_kind','id')) if item.get('v4_style') else old[item['structure_id']]
            desc=subject(s,item['params']);desc=desc if desc.startswith('the ') else 'the '+desc
            text=sentence.replace(desc,'__SUBJECT__')
            for literal in item['params'].values():
                if isinstance(literal,str):text=text.replace(repr(literal),'__LITERAL__')
            if re.search(r'\b(value|entity_id|post_text|user_name|associated_count|positive_percentage|identity|extra_field)\b',text,re.I):aliases.append(item['instance_id'])
            if re.search(r'\b(member|standing points|node|edge|relationship|route|connection|path)\b',text,re.I):vocabulary.append(item['instance_id'])
            for literal in item['params'].values():text=text.replace(str(literal),'__PARAM__')
            frames[(item['structure_id'],norm(text))].append(item['instance_id'])
            if item.get('v4_output_attribute'):
                expected={'reputation':'reputation','count':'usage count','score':'score','viewCount':'view count','creationDate':'date','location':'location'}[item['v4_output_attribute']]
                if expected not in sentence.casefold():field_mismatches.append(item['instance_id'])
        current_i=(V4/('instances_v4_train'+suffix+'.jsonl')).read_bytes().splitlines(keepends=True)
        original_i=(V4/('before_review_'+batch)/('instances_v4_train'+suffix+'.jsonl')).read_bytes().splitlines(keepends=True)
        findings=json.loads((V4/'review_findings.json').read_text())[batch]
        replacements=set(findings['answer_stated_in_question']);original_q=(V4/('before_review_'+batch)/('questions_v4_train'+suffix+'.jsonl')).read_bytes().splitlines(keepends=True)
        current_q=(V4/('questions_v4_train'+suffix+'.jsonl')).read_bytes().splitlines(keepends=True)
        qallowed=replacements|set(findings['range_with_equal_bounds'])
        checks={'questions_written':len(questions),'instances':len(rows),'complete_coverage':set(byid)=={i['instance_id'] for i in rows},'duplicate_ids':len(questions)-len(byid),'heldout_overlaps':[q['instance_id'] for q in questions if norm(q['question']) in held_text],'alias_mentions':aliases,'prohibited_vocabulary':vocabulary,'replacement_field_wording_mismatches':field_mismatches,'lookup_scalar_parameter_echo_ids':[i['instance_id'] for i in rows if i['shape']['aggregation']=='none' and parameter_echo(i)],'literal_scalar_parameter_equality_rejections':[i['instance_id'] for i in rows if parameter_echo(i)],'equal_bound_wording_remaining':[q['instance_id'] for q in questions if re.search(r'between ([\d.-]+) and \1 inclusive',q['question'])],'raw_bytes_preserved_for_untouched_instances':all(a==b for a,b in zip(original_i,current_i) if json.loads(a)['instance_id'] not in replacements),'raw_bytes_preserved_for_untouched_written_questions':all(line in current_q for line in original_q if json.loads(line)['instance_id'] not in qallowed),'hints_with_hint':sum('hint' in i for i in rows),'hint_share':sum('hint' in i for i in rows)/len(rows)}
        assert checks['complete_coverage'] and not checks['duplicate_ids'] and not checks['heldout_overlaps'] and not aliases and not vocabulary and not field_mismatches and not checks['lookup_scalar_parameter_echo_ids'] and not checks['equal_bound_wording_remaining']
        assert checks['raw_bytes_preserved_for_untouched_instances'] and checks['raw_bytes_preserved_for_untouched_written_questions']
        reportfile=V4/('report.json' if batch=='batch1' else 'report_batch2.json');report=json.loads(reportfile.read_text());report['final_question_checks']=checks;report['questions_written']=len(questions)
        report['status']=('batch 1 FINAL' if batch=='batch1' else 'batch 2 complete')+'; requested review repairs verified; frozen aggregate equality exceptions declared'
        report['next_step']='Training handoff. Ask owner whether coincidental numeric equality in frozen aggregates should be grandfathered or replaced in a later authorized revision.'
        if batch=='batch2':
            report['question_checkpoint']['next_queue_index']=len(rows)
            report['checks']['first_batch_unchanged']=all(hashlib.sha256((V4/name).read_bytes()).hexdigest()==sha for name,sha in report['first_batch_hashes'].items())
            assert report['checks']['first_batch_unchanged']
        reportfile.write_text(json.dumps(report,indent=2)+'\n');batches.append({'batch':batch}|checks)
        all_text.extend(norm(q['question']) for q in questions);all_ids.extend(q['instance_id'] for q in questions)
    summary={'batches':batches,'combined_questions':len(all_text),'duplicate_questions_across_batches':len(all_text)-len(set(all_text)),'duplicate_instance_ids_across_batches':len(all_ids)-len(set(all_ids)),'identical_normalized_sentence_frames_same_structure':[ids for ids in frames.values() if len(ids)>1]}
    assert not summary['duplicate_questions_across_batches'] and not summary['duplicate_instance_ids_across_batches']
    (V4/'final_question_audit.json').write_text(json.dumps(summary,indent=2)+'\n');checkpoint('Final reviewed question-set audit',summary);assert_frozen();print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
