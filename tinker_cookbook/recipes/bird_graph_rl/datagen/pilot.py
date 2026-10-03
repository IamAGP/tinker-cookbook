"""Sixty individually authored pilot prompts, bound to verified graph instances."""
from __future__ import annotations
import json
import re
from .generate import HERE, Params, write_jsonl
from .structures import PROPERTIES, enumerate_structures, paths


def main() -> None:
    out = HERE/'out'
    instances = [json.loads(line) for line in (out/'instances.jsonl').read_text().splitlines()]
    structures = {s.structure_id:s for s in enumerate_structures()}
    path_list = paths()
    selected = []
    questions = []
    def pick(path_index: int, mode: str) -> Params:
        eligible = [i for i in instances if structures[i['structure_id']].path == path_list[path_index]
                    and structures[i['structure_id']].mode == mode]
        if not eligible:
            raise ValueError(f'Pilot structure unavailable: path={path_index} mode={mode}')
        # Select an informative nonzero result when possible; never use evaluation data.
        eligible.sort(key=lambda i:(not any(isinstance(v,(int,float)) and v != 0
                                           for r in i['rows'] for v in r.values()),i['instance_id']))
        i = eligible[0]
        selected.append(i)
        return i['params']
    def add(text: str) -> None:
        questions.append({'instance_id':selected[-1]['instance_id'],'question':text})
    # 0 edges. Each prompt has its own wording and domain-specific requested calculation.
    p=pick(0,'count'); add(f"How many members have standing points from {p['lower']} through {p['upper']}, inclusive? Return the total in `value`.")
    p=pick(0,'sum'); add(f"Add up the standing points of members within the inclusive {p['lower']}–{p['upper']} band of standing points. I need a single column, `value`.")
    p=pick(0,'avg'); add(f"Give the mean standing points, as `value`, among members whose standing points are at least {p['lower']} and at most {p['upper']}.")
    p=pick(0,'top'); add(f"Build a leaderboard of up to {p['k']} members in the standing points interval [{p['lower']}, {p['upper']}]. List `entity_id` (member number) and `value` (standing points), highest standing points first; order equal totals of standing points by member number ascending.")
    p=pick(1,'count'); add(f"Within the inclusive point total interval {p['lower']} to {p['upper']}, what is the number of contributions? Call the total column `value`.")
    p=pick(1,'sum'); add(f"For contributions scoring between {p['lower']} and {p['upper']} inclusive, report their combined point total in `value`.")
    p=pick(1,'avg'); add(f"What average point total do contributions in [{p['lower']}, {p['upper']}] achieve? Supply only `value`.")
    p=pick(3,'top'); add(f"Which {p['k']} topics lead the stored usage total interval from {p['lower']} to {p['upper']} inclusive? Return up to that many rows with `entity_id` for the topic number and `value` for its saved usage tally, descending by tally and ascending by number for ties.")
    p=pick(2,'count'); add(f"Tally inquiries with point totals no lower than {p['lower']} and no higher than {p['upper']}; put the result under `value`.")
    p=pick(2,'sum'); add(f"I want the sum of inquiry point totals in the closed interval [{p['lower']}, {p['upper']}], returned as `value`.")
    p=pick(2,'avg'); add(f"Restrict attention to inquiries scoring {p['lower']} through {p['upper']} inclusive. Return their mean point total in the column `value`.")
    p=pick(3,'sum'); add(f"Sum the stored usage tallies for topics whose stored usage tally falls between {p['lower']} and {p['upper']} inclusive. Return the total as `value`, using saved tallies rather than recounting attached contributions.")
    # 1 edge. Author's posts and direct outbound links.
    p=pick(4,'detail'); add(f"List the contributions authored by member number {p['anchor']}, with their point totals. Use `entity_id` for each contribution number and `value` for its point total; list each contribution once in number order.")
    p=pick(4,'count'); add(f"How many authorship connections associate member number {p['anchor']} with contributions? Return `value`.")
    p=pick(4,'distinct'); add(f"For member number {p['anchor']}, tally different authored contributions, ignoring repeated connections. The sole output is `value`.")
    p=pick(4,'sum'); add(f"Calculate the combined point total of contributions by member number {p['anchor']}. Include a point total for each authorship connection and report `value`.")
    p=pick(4,'avg'); add(f"Member number {p['anchor']}: what is the average point total of their authored contributions, weighting one occurrence per authorship connection? Return `value`.")
    p=pick(4,'min'); add(f"What is the lowest point total among contributions authored by member number {p['anchor']}? Call that result `value`.")
    p=pick(4,'max'); add(f"Report `value`, the greatest point total recorded for any contribution authored by member number {p['anchor']}.")
    p=pick(4,'group'); add(f"For each contribution by member number {p['anchor']}, show its contribution number as `entity_id` and the number of authorship connections from that member as `value`. Sort by contribution number.")
    p=pick(4,'top'); add(f"Rank the contributions authored by member number {p['anchor']} and return at most {p['k']}. Show distinct `entity_id`/`value` pairs for contribution number and point total, decreasing point total, then increasing contribution number.")
    p=pick(4,'bottom'); add(f"Find the lowest-scoring contribution by member number {p['anchor']}, choosing the smaller contribution number if point totals tie. Return `entity_id` for that number and `value` for the point total.")
    p=pick(7,'count'); add(f"How many outbound contribution links originate at contribution number {p['anchor']}? Return the link tally in `value`.")
    p=pick(7,'max'); add(f"Among the contributions directly linked to from contribution number {p['anchor']}, what is the maximum point total? Respond with the column `value`.")
    # 2 edges. Member -> authored comment -> its attached post.
    p=pick(10,'detail'); add(f"Where has member number {p['anchor']} commented? Give each distinct attached contribution's number in `entity_id` and its point total in `value`, sorted by contribution number.")
    p=pick(10,'count'); add(f"Tally complete connections from member number {p['anchor']} through a remark they authored to the contribution carrying it. Return `value`; multiple remarks on one contribution are tallied separately.")
    p=pick(10,'distinct'); add(f"On how many different contributions has member number {p['anchor']} written remarks? Put the distinct-contribution tally in `value`.")
    p=pick(10,'sum'); add(f"Total the point totals of contributions commented on by member number {p['anchor']}, counting a contribution again for every authored-remark attachment. Output `value`.")
    p=pick(10,'avg'); add(f"Compute `value`: the average attached-contribution point total per complete authored-remark connection for member number {p['anchor']}, retaining repeated contributions.")
    p=pick(10,'min'); add(f"Looking at contributions carrying remarks by member number {p['anchor']}, identify the smallest contribution point total and return it as `value`.")
    p=pick(10,'max'); add(f"Return the highest contribution point total encountered through remarks written by member number {p['anchor']}; the output column is `value`.")
    p=pick(10,'group'); add(f"Break down member number {p['anchor']}'s authored-remark attachments by contribution. Return `entity_id` (contribution number) and `value` (number of complete attachments), in contribution-number order.")
    p=pick(10,'top'); add(f"Of the distinct contributions commented on by member number {p['anchor']}, show up to {p['k']} with the greatest point totals. Use `entity_id` and `value` for contribution number and point total; sort by descending point total and then ascending contribution number.")
    p=pick(10,'bottom'); add(f"Which contribution carrying a remark by member number {p['anchor']} has the lowest point total? Return `entity_id` and `value` for its number and point total, using the lowest number to resolve a tie.")
    p=pick(10,'ratio'); add(f"What percentage of member number {p['anchor']}'s authored-remark attachments lead to contributions with positive point totals? Tally complete attachments, retaining repeated contributions and including contributions missing a point total in the denominator. Return `percentage` on a zero-to-one-hundred scale.")
    p=pick(10,'year'); add(f"For member number {p['anchor']}'s authored-remark attachments, average the attached contributions' point totals only when those contributions were created in calendar years {p['year']} through {p['end_year']} inclusive. Preserve repeated attachments; return `value`.")
    # 3 edges. Member's post -> its outbound linked post -> that post's author.
    p=pick(17,'detail'); add(f"Starting with contributions by member number {p['anchor']}, follow an outbound contribution link and find the linked contribution's author. List distinct author-number/standing points pairs as `entity_id` and `value`, ordered by author number. A connection cannot be reused within one route.")
    p=pick(17,'count'); add(f"How many complete routes run from member number {p['anchor']} through one of their contributions, an outbound linked contribution, and that linked contribution's author? Return `value`; tally routes separately and do not reuse a connection within a route.")
    p=pick(17,'distinct'); add(f"How many distinct authors are reached by following outbound links from member number {p['anchor']}'s contributions and then taking the linked contributions' authors? Return `value`; no route may reuse a connection.")
    p=pick(17,'sum'); add(f"Sum the standing points of authors reached from member number {p['anchor']}'s contributions via outbound contribution links. Include the standing total once per complete route, even for repeated authors, without reusing a connection within a route. Output `value`.")
    p=pick(17,'avg'); add(f"For routes from member number {p['anchor']} to their contributions, then outbound linked contributions, then the linked contributions' authors, report mean author standing points in `value`. Weight each full route equally; connections within it must differ.")
    p=pick(17,'min'); add(f"Find the fewest standing points among authors of contributions linked to from member number {p['anchor']}'s contributions. Use routes with no repeated connection and return `value`.")
    p=pick(17,'max'); add(f"What is the largest author total of standing points reachable by an outbound link from a contribution authored by member number {p['anchor']}? Report `value`; do not reuse any connection along the route.")
    p=pick(17,'group'); add(f"Tabulate authors of the contributions linked to from member number {p['anchor']}'s contributions. For each author, return `entity_id` (member number) and `value` (number of complete routes), sorted by member number. Each route uses distinct connections.")
    p=pick(17,'top'); add(f"Show up to {p['k']} authors with the most standing points of contributions reached through outbound links from member number {p['anchor']}'s contributions. Return distinct `entity_id`/`value` pairs for author number and standing points, ordered by standing points descending then number ascending; use routes without repeated connections.")
    p=pick(17,'bottom'); add(f"Among authors of contributions linked to from member number {p['anchor']}'s contributions, select the one with lowest standing points, breaking ties by lowest member number. Return `entity_id` and `value` for number and standing points. A qualifying route may not repeat a connection.")
    p=pick(17,'having'); add(f"Which authors can be reached with a total of complete routes of at least {p['threshold']} through member number {p['anchor']}'s contributions and their outbound links? Return `entity_id` for author number and `value` for the route tally, ordered by number; within a route, connections must differ.")
    p=pick(17,'named'); add(f"For the uniquely named member {p['name']!r}, total the standing points of authors of contributions linked to from their contributions. Repeat an author's standing points for each complete route and use distinct connections within a route. Return only `value`.")
    # 4 edges. Prior route followed by a comment written by the reached author.
    p=pick(23,'detail'); add(f"Take contributions by member number {p['anchor']}, their outbound linked contributions, the linked contributions' authors, and remarks written by those authors. List distinct remark-number/point total pairs in `entity_id` and `value`, sorted by remark number. Use no connection twice in one route.")
    p=pick(23,'count'); add(f"Tally complete routes from member number {p['anchor']} to an authored contribution, an outbound linked contribution, its author, and a remark by that author. Return `value`, retaining repeated remarks reached by different routes and forbidding reused connections within a route.")
    p=pick(23,'distinct'); add(f"How many different remarks were written by authors of contributions linked to from member number {p['anchor']}'s contributions? Return `value`; qualifying routes must have no repeated connection.")
    p=pick(23,'sum'); add(f"Accumulate remark point totals along all routes from member number {p['anchor']} through an authored contribution, an outbound linked contribution, its author, and a remark they authored. Include point totals once per complete route; do not reuse connections within it. Output `value`.")
    p=pick(23,'avg'); add(f"Return `value`, the mean remark point total per complete route through member number {p['anchor']}'s contributions, their outbound linked contributions, the linked contributions' authors, and those authors' remarks. Repeated remarks retain their route weights; connections in a route are distinct.")
    p=pick(24,'min'); add(f"From member number {p['anchor']}, follow a remark they authored, the contribution it is attached to, an outbound linked contribution, and that linked contribution's author. What is the fewest standing points of those authors? Return `value`; no route may repeat a connection.")
    p=pick(23,'max'); add(f"Find the highest remark point total obtainable from authors of contributions linked to by member number {p['anchor']}'s contributions. The output column is `value`; each complete route must use distinct connections.")
    p=pick(23,'group'); add(f"For every remark reached from member number {p['anchor']}'s contributions through outbound linked contributions and their authors, give `entity_id` (remark number) and `value` (complete-route tally). Order by remark number and tally only routes that never reuse a connection.")
    p=pick(23,'top'); add(f"Retrieve up to {p['k']} best-scoring distinct remarks written by authors of contributions linked to from member number {p['anchor']}'s contributions. Return `entity_id` for remark number and `value` for point total, highest point totals first and lowest numbers first on ties. Qualifying routes cannot repeat connections.")
    p=pick(24,'bottom'); add(f"Among authors reached via member number {p['anchor']}'s remarks, the contributions carrying them, and outbound links from those contributions, select the author with lowest standing points. Break ties by smallest member number and return `entity_id` (member number) and `value` (standing points). Connections within a qualifying route must differ.")
    p=pick(23,'null'); add(f"From member number {p['anchor']}'s contributions, follow outbound links, take the linked contributions' authors, then their remarks. Sum remark point totals only where the remark's saved author-designation wording is missing; tally every complete route with distinct connections and return `value`.")
    p=pick(23,'named'); add(f"Starting from the uniquely named member {p['name']!r}, traverse their contributions, outbound linked contributions, those contributions' authors, and the remarks those authors authored. Sum the remark point totals once per complete route, with no reused connections, and report `value`.")
    assert len(questions) == 60
    assert len({q['instance_id'] for q in questions}) == 60
    for i,q in zip(selected,questions,strict=True):
        for col in i['rows'][0]:
            assert f'`{col}`' in q['question']
    schema_words = set(PROPERTIES) | {v for properties in PROPERTIES.values() for v in properties[:3] if v}
    schema_words.update('OWNS LAST_EDITED ANSWERS ACCEPTED TAGGED HAS_EXCERPT HAS_WIKI LINKS_TO WROTE ON_POST CAST MADE REVISES EARNED creationDate lastAccessDate websiteUrl aboutMe views upVotes downVotes accountId age profileImageUrl postTypeId viewCount body lastActivityDate lastEditDate communityOwnedDate closedDate answerCount commentCount favoriteCount ownerDisplayName lastEditorDisplayName voteTypeId bountyAmount revisionGuid userDisplayName postLinkId linkTypeId badgeId date'.split())
    for question in questions:
        assert not any(re.search(r'\b'+re.escape(word)+r'\b',question['question'],re.I) for word in schema_words), question['instance_id']
    write_jsonl(out/'pilot_questions.jsonl',questions)
    # Include bindings for review while keeping the requested output format minimal.
    write_jsonl(out/'pilot_review.jsonl',[{'instance_id':i['instance_id'],'hops':i['hops'],
        'mode':structures[i['structure_id']].mode,'cypher':i['cypher'],'params':i['params'],
        'rows_preview':i['rows'][:3],'question':q['question']}
        for i,q in zip(selected,questions,strict=True)])
    print('Wrote 60 individually authored questions: 12 per hop count.')


if __name__ == '__main__':
    main()
