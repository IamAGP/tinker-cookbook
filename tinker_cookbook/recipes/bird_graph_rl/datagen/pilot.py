"""Individually authored amended pilot: ordinary vocabulary, no output aliases."""
from __future__ import annotations
import json
import re
from .generate import HERE, write_jsonl
from .structures import enumerate_structures, PROPERTIES


def subject(s, p):
    root=s.path.labels[0]
    nouns={'User':'users','Post':'posts','Question':'questions','Answer':'answers','Tag':'tags'}
    if s.anchor=='range':
        metric='reputation' if root=='User' else 'stored usage count' if root=='Tag' else 'score'
        anchor=f"{nouns[root]} with {metric} between {p['lower']} and {p['upper']} inclusive"
    elif 'name' in p:
        anchor=f"the user {p['name']!r}" if root=='User' else f"the tag {p['name']!r}"
    elif 'title' in p: anchor=f"{nouns[root]} titled {p['title']!r}"
    elif 'badge' in p: anchor=f"holders of the {p['badge']!r} badge"
    elif 'date' in p: anchor=f"{nouns[root]} {'who joined' if root=='User' else 'created'} on {p['date']}"
    else: anchor=f"the {nouns[root][:-1]} with ID {p['anchor']}"
    d=s.description
    if not s.path.hops: d=anchor
    else:
        d=d.replace('the selected users',anchor).replace('the selected posts',anchor).replace('the selected questions',anchor).replace('the selected answers',anchor).replace('the selected tags',anchor).replace('holders of the selected badge',anchor)
    if s.mode=='year': d+=f", created in years {p['year']} through {p['end_year']} inclusive"
    if s.mode in ('null','not_null'):
        field=PROPERTIES[s.label][2]
        word={'location':'location','title':'title','closedDate':'closing date','lastEditDate':'last edit date','userDisplayName':'saved author display name'}.get(field,field)
        d+=' with '+('no recorded ' if s.mode=='null' else 'a recorded ')+word
    if s.mode in ('contains','starts'):
        word='display name' if s.label=='User' else 'tag name' if s.label=='Tag' else 'title'
        d+=f" whose {word} "+('contains' if s.mode=='contains' else 'starts with')+f" {p['text']!r} (case-sensitive)"
    if s.mode=='label': d+=' that are questions'
    if s.mode=='exists': d+=' with at least one comment'
    if s.mode=='negation': d+=' with no comments'
    return d


def main() -> None:
    out=HERE/'out'
    known={s.structure_id:s for s in enumerate_structures()}
    instances=[json.loads(l) for l in (out/'instances.jsonl').read_text().splitlines()]
    schedules={0:['sum','avg','top','argmax','sum','avg'],
        1:['detail','distinct','sum','avg','min','max','top','bottom','argmax','detail'],
        2:['detail','distinct','sum','avg','min','max','top','bottom','argmax','ratio','entity_group','entity_having','exists','negation'],
        3:['detail','distinct','sum','avg','min','max','top','bottom','argmax','comparison','entity_group','entity_having','contains','year'],
        4:['detail','distinct','sum','avg','min','max','top','bottom','argmax','named','entity_group','entity_having','starts','null','not_null','comparison']}
    picked=[]; used=set()
    for hop,modes in schedules.items():
        for mode in modes:
            eligible=[i for i in instances if i['hops']==hop and known[i['structure_id']].mode==mode and i['structure_id'] not in used]
            if not eligible: raise ValueError(f'No distinct pilot structure for hop={hop} mode={mode}')
            eligible.sort(key=lambda i:(known[i['structure_id']].anchor=='id',not any(isinstance(v,(int,float)) and v!=0 for r in i['rows'] for v in r.values()),i['instance_id']))
            i=eligible[0]; picked.append(i); used.add(i['structure_id'])
    # The following sixty full questions were separately authored. Shared subject
    # fragments bind exact filters; no two selected instances share a structure.
    q=[]
    def add(index, sentence): q.append({'instance_id':picked[index]['instance_id'],'question':sentence})
    def d(index): return subject(known[picked[index]['structure_id']],picked[index]['params'])
    def m(index): return 'stored tag usage count' if known[picked[index]['structure_id']].metric=='count' else known[picked[index]['structure_id']].metric
    def k(index): return picked[index]['params']['k']
    def associated(index):
        s=known[picked[index]['structure_id']]
        return {'Post':'posts','Question':'questions','Answer':'answers','User':'users','Comment':'comments','PostHistory':'revision entries','Vote':'votes','Tag':'tags','Badge':'badges'}[s.path.labels[s.previous]]
    add(0,f'What is the combined {m(0)} of {d(0)}?')
    add(1,f'Among {d(1)}, how high is the average {m(1)}?')
    add(2,f'Give me the top {k(2)} {d(2)} by {m(2)}, including their names or titles and that measurement.')
    add(3,f'Which of {d(3)} has the greatest {m(3)}? Show its name or text and the measurement.')
    add(4,f'Add together the {m(4)} for {d(4)}. What total does that give?')
    add(5,f'I am comparing {d(5)}. What is their mean {m(5)}?')
    add(6,f'Please list {d(6)} with their {m(6)}.')
    add(7,f'How many different {d(7)} are there?')
    add(8,f'For {d(8)}, calculate the total {m(8)}, counting each item once.')
    add(9,f'What average {m(9)} do {d(9)} have?')
    add(10,f'Find the smallest {m(10)} among {d(10)}.')
    add(11,f'What is the highest {m(11)} recorded for {d(11)}?')
    add(12,f'Rank {d(12)} by {m(12)} and show up to {k(12)} of the best, with their identifying names or text and measurement.')
    add(13,f'Pick the lowest-{m(13)} item among {d(13)}; include its name or text and the measurement.')
    add(14,f'I want the name or text and {m(14)} of the highest-ranked item among {d(14)}.')
    add(15,f'Can you show {d(15)} and the {m(15)} for each?')
    add(16,f'List {d(16)}, along with their {m(16)}.')
    add(17,f'How large is the set of distinct {d(17)}?')
    add(18,f'What total {m(18)} comes from {d(18)}? Include each qualifying item once.')
    add(19,f'Give the mean {m(19)} of {d(19)}.')
    add(20,f'Among {d(20)}, what is the minimum {m(20)}?')
    add(21,f'Tell me the maximum {m(21)} for {d(21)}.')
    add(22,f'Which {k(22)} {d(22)} rank highest for {m(22)}? Include names or text and the measurement.')
    add(23,f'Show the name or text and {m(23)} of the lowest-ranked item among {d(23)}.')
    add(24,f'Identify the item with the largest {m(24)} among {d(24)}, and give its name or text and measurement.')
    add(25,f'What percentage of the distinct {d(25)} have positive {m(25)}? Include missing measurements in the denominator.')
    add(26,f'For each of {d(26)}, show its name or text and how many distinct qualifying {associated(26)} it has.')
    add(27,f"Which of {d(27)} have at least {picked[27]['params']['threshold']} distinct qualifying {associated(27)}? List them with those totals.")
    add(28,f'Count the different {d(28)}.')
    add(29,f'How many distinct {d(29)} can you find?')
    add(30,f'I would like a list of {d(30)} and their {m(30)}.')
    add(31,f'How many different {d(31)} qualify?')
    add(32,f'Total up the {m(32)} of {d(32)}, once per qualifying item.')
    add(33,f'What mean {m(33)} characterizes {d(33)}?')
    add(34,f'What is the least {m(34)} seen among {d(34)}?')
    add(35,f'Find the greatest {m(35)} for {d(35)}.')
    add(36,f'Give a leaderboard of up to {k(36)} {d(36)} using {m(36)}, with names or text and measurements.')
    add(37,f'Who or what has the lowest {m(37)} among {d(37)}? Supply the name or text and that measurement.')
    add(38,f'For {d(38)}, show the name or text of the highest-{m(38)} item together with its measurement.')
    p=picked[39]['params']; add(39,f"How much larger is the total {m(39)} of {known[picked[39]['structure_id']].description.replace('the selected users','each user')} for {p['name']!r} than for {p['other_name']!r}? Count each qualifying item once per user.")
    add(40,f'Break down {d(40)} by the number of distinct qualifying {associated(40)} for each. Show their names or text and totals.')
    add(41,f"List {d(41)} with at least {picked[41]['params']['threshold']} distinct qualifying {associated(41)}, together with their totals.")
    add(42,f'How many different {d(42)} meet that text condition?')
    add(43,f'What average {m(43)} do {d(43)} achieve?')
    add(44,f'Show {d(44)} with their {m(44)}; include each item once.')
    add(45,f'What is the number of distinct {d(45)}?')
    add(46,f'Calculate a combined {m(46)} for {d(46)}, without counting any item twice.')
    add(47,f'I need the average {m(47)} across {d(47)}.')
    add(48,f'Report the lowest {m(48)} found among {d(48)}.')
    add(49,f'How high does {m(49)} go for {d(49)}?')
    add(50,f'Pick up to {k(50)} best-ranked {d(50)} by {m(50)} and show their names or text with measurements.')
    add(51,f'Find the name or text and {m(51)} of the least highly ranked item among {d(51)}.')
    add(52,f'Which item leads {d(52)} for {m(52)}? Show its name or text and measurement.')
    add(53,f'What is the total {m(53)} for {d(53)}, counting each qualifying item once?')
    add(54,f'Show the names or text of {d(54)} and their numbers of distinct qualifying {associated(54)}.')
    add(55,f"Among {d(55)}, return those with at least {picked[55]['params']['threshold']} distinct qualifying {associated(55)} and show their totals.")
    add(56,f'How many distinct {d(56)} match the stated prefix?')
    add(57,f'Sum the {m(57)} of {d(57)} once per item.')
    add(58,f'What is the mean {m(58)} among {d(58)}?')
    p=picked[59]['params']; add(59,f"Compare the total {m(59)} for {known[picked[59]['structure_id']].description.replace('the selected users','each user')} between {p['name']!r} and {p['other_name']!r}: give the first total minus the second, with each qualifying item counted once per user.")
    for i,text in zip(picked,q,strict=True):
        s=known[i['structure_id']]
        entity={'User':'user','Tag':'tag','Comment':'comment','Answer':'answer','Question':'question','Post':'post'}[s.label]
        field={'user_name':'display name','tag_name':'tag name','comment_text':'first 120 characters of comment text','answer_text':'first 120 characters of the answer body','post_text':'title, or the first 120 characters of the body when no title is recorded'}[s.display[1]]
        sentence=text['question']
        sentence=sentence.replace('names or titles',field+'s' if s.label in ('User','Tag') else field).replace('identifying names or text',field).replace('names or text',field+'s' if s.label in ('User','Tag') else field).replace('name or text',field)
        sentence=sentence.replace('Who or what','Which '+entity).replace('item',entity)
        text['question']=sentence
    assert len(q)==60 and len(used)==len(q)
    for i,question in zip(picked,q,strict=True):
        audited=question['question']
        for literal in i['params'].values():
            if isinstance(literal,str): audited=audited.replace(repr(literal),'')
        assert not re.search(r'\b(node|edge|relationship|route|connection|path|value|entity_id)\b',audited,re.I)
        assert not re.search(r'\b[a-z]+[A-Z][a-zA-Z]*\b',audited)
        assert set(question)=={'instance_id','question'}
    write_jsonl(out/'pilot_questions.jsonl',q)
    write_jsonl(out/'pilot_review.jsonl',[dict(instance_id=i['instance_id'],hops=i['hops'],cypher=i['cypher'],params=i['params'],rows=i['rows'][:3],question=text['question']) for i,text in zip(picked,q,strict=True)])
    print(json.dumps({'questions':len(q),'distinct_structures':len(used),'by_hop':{h:sum(i['hops']==h for i in picked) for h in schedules}}))


if __name__=='__main__': main()
