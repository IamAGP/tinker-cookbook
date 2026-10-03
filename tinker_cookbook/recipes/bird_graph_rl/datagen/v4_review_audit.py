"""Byte-preservation, live-answer and boundary audits for targeted review edits."""
from __future__ import annotations
from collections import Counter
import hashlib,json,re
from dotenv import dotenv_values
from neo4j import GraphDatabase
from .generate import ReadGraph,REPO,canonical_rows,rejection,HERE
from .v4 import V4,OUT,load,forbidden,assert_frozen
from .structures import components
from .v4_review_fix import parameter_echo,checkpoint


def audit(batch,final=False):
    suffix='' if batch=='batch1' else '_batch2'
    ip=V4/('instances_v4_train'+suffix+'.jsonl');qp=V4/('questions_v4_train'+suffix+'.jsonl');sp=V4/('structures_v4_train'+suffix+'.jsonl')
    current_lines=ip.read_text().splitlines(keepends=True);rows=[json.loads(line) for line in current_lines]
    questions=[json.loads(line) for line in qp.read_text().splitlines()]
    before=(V4/('before_review_'+batch)/ip.name).read_text().splitlines(keepends=True)
    before_q=(V4/('before_review_'+batch)/qp.name).read_text().splitlines(keepends=True)
    findings=json.loads((V4/'review_findings.json').read_text())[batch];target=set(findings['answer_stated_in_question'])
    old_ss,old_ii=load();blocked=forbidden(old_ss);heldsig={s['signature'] for s in old_ss if s['split']=='heldout_structure'}
    ss=[json.loads(line) for line in sp.read_text().splitlines()]
    class Signature:
        def __init__(self,value):self.signature=value
    old_rows={json.loads(line)['instance_id']:json.loads(line) for line in before}
    replacement=json.loads((V4/('review_replacements_'+batch+'.json')).read_text())['replacements']
    normalized=lambda text:re.sub(r'\s+',' ',text).strip().casefold()
    held_ids={i['instance_id'] for i in old_ii if i['split']!='train'}
    heldq={normalized(q['question']) for q in [json.loads(line) for line in (OUT/'questions.jsonl').read_text().splitlines()] if q['instance_id'] in held_ids}
    single_flags=[i['instance_id'] for i in rows if parameter_echo(i)]
    echo_lookups=[i['instance_id'] for i in rows if i['shape']['aggregation']=='none' and parameter_echo(i)]
    allowed_questions=target|set(findings['range_with_equal_bounds'])
    changed_lines=sum(a!=b for a,b in zip(before,current_lines))
    current_q_byid={q['instance_id']:q for q in questions}
    unchanged_q=all(current_q_byid.get(json.loads(line)['instance_id'])==json.loads(line) for line in before_q if json.loads(line)['instance_id'] not in allowed_questions)
    unchanged_q_bytes=all(line in qp.read_text().splitlines(keepends=True) for line in before_q if json.loads(line)['instance_id'] not in allowed_questions)
    checks={'replacements':len(replacement),'untouched_instances_byte_identical':all(a==b for a,b in zip(before,current_lines) if json.loads(a)['instance_id'] not in target),'unchanged_instance_lines':sum(a==b for a,b in zip(before,current_lines)),'changed_instance_lines':changed_lines,'unaffected_questions_byte_identical':unchanged_q and unchanged_q_bytes,'same_mix_cells':all(old_rows[iid]['shape']==item['shape'] and old_rows[iid]['hops']==item['hops'] for iid,item in replacement.items()),'no_parameter_echo_lookups':not echo_lookups,'literal_scalar_parameter_equality_rejections':single_flags,'literal_rule_passes_entire_batch':not single_flags,'declared_freeze_exceptions':single_flags,'no_heldout_signature':all(s['signature'] not in heldsig for s in ss),'no_heldout_component_introduced':not set().union(*(components(Signature(s['signature'])) for s in ss))&blocked,'heldout_question_overlaps':[q['instance_id'] for q in questions if normalized(q['question']) in heldq],'duplicate_questions':len(questions)-len({normalized(q['question']) for q in questions}),'questions_written':len(questions),'complete_coverage':{q['instance_id'] for q in questions}=={i['instance_id'] for i in rows},'equal_bound_wording_remaining':[q['instance_id'] for q in questions if re.search(r'between ([\d.-]+) and \1 inclusive',q['question'])]}
    first=[json.loads(line) for line in (V4/'instances_v4_train.jsonl').read_text().splitlines()];second=[json.loads(line) for line in (V4/'instances_v4_train_batch2.jsonl').read_text().splitlines()]
    checks['combined_max_per_structure']=max(Counter(i['structure_id'] for i in first+second).values())
    checks['batch_ids_disjoint']=not {i['instance_id'] for i in first}&{i['instance_id'] for i in second}
    assert checks['untouched_instances_byte_identical'] and checks['unaffected_questions_byte_identical'] and checks['same_mix_cells'] and not echo_lookups and checks['no_heldout_signature'] and checks['no_heldout_component_introduced']
    assert not checks['heldout_question_overlaps'] and not checks['duplicate_questions'] and not checks['equal_bound_wording_remaining'] and checks['combined_max_per_structure']<=5 and checks['batch_ids_disjoint']
    config=dotenv_values(REPO/'.env');inspections=[]
    with GraphDatabase.driver(str(config['BIRD_NEO4J_URI']),auth=(str(config['BIRD_NEO4J_USER']),str(config['BIRD_NEO4J_PASSWORD']))) as driver:
        graph=ReadGraph(driver)
        for item in rows:
            result,ms=graph.execute(item['cypher'],item['params'])
            inspections.append({'instance_id':item['instance_id'],'matches_saved':canonical_rows(result)==canonical_rows(item['rows']),'rejection':rejection(result,ms)})
    checks['live_executed']=len(inspections);checks['live_matched']=sum(i['matches_saved'] for i in inspections);checks['live_rejections']=dict(Counter(i['rejection'] for i in inspections if i['rejection']))
    assert checks['live_matched']==len(rows) and not checks['live_rejections']
    report_file=V4/('report.json' if batch=='batch1' else 'report_batch2.json');report=json.loads(report_file.read_text())
    report['review_fixes']=checks;report['questions_written']=len(questions)
    report['status']=('batch 1 FINAL: specific review findings resolved; frozen aggregate numeric-equality exceptions declared' if final else 'batch 2 review fixes verified; question writing in progress')
    report['literal_scalar_guard_note']='The unconditional scalar equality guard rejects these coincidental aggregate answers. They remain unchanged under the explicit preservation rule; new replacements and unaggregated lookups pass the guard.'
    report_file.write_text(json.dumps(report,indent=2)+'\n')
    (V4/('review_audit_'+batch+'.json')).write_text(json.dumps(checks,indent=2)+'\n')
    checkpoint(('BATCH 1 FINAL' if final else 'Batch 2 targeted review fixes verified'),checks)
    if single_flags:
        with (HERE/'QUESTIONS.md').open('a') as f:f.write('\n## Literal scalar-equality audit and frozen aggregates — '+batch+'\n\n'+json.dumps({'flagged_ids':single_flags,'count':len(single_flags)},indent=2)+'\n\nThese aggregate answers happen to equal numeric filter parameters. The requested unconditional audit rejects them, but the explicit freeze forbids changing them in this targeted repair. They are retained as disclosed exceptions. Please confirm whether the broader rule should grandfather such aggregates or a later change should replace them.\n')
    assert_frozen();print(json.dumps(checks,indent=2))


if __name__=='__main__':
    import sys
    audit(sys.argv[1],sys.argv[1]=='batch1')
