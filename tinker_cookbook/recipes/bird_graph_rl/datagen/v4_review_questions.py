"""Individually authored corrections for the independent review's specific lookups."""
from .v4_review_fix import V4
import json


def questions(batch):
    ids=json.loads((V4/'review_findings.json').read_text())[batch]['answer_stated_in_question']
    replacements=json.loads((V4/('review_replacements_'+batch+'.json')).read_text())['replacements']
    def p(index):
        item=replacements[ids[index]]
        return repr(item['params'].get('name',item['params'].get('title')))
    if batch=='batch1':
        sentences=[
            f'What reputation does the user {p(0)} have?',
            f'When was the user account {p(1)} created? Give the date and time.',
            f'How much reputation is recorded for {p(2)}?',
            f'For questions titled {p(3)}, list the different scores.',
            f'What distinct view counts are recorded for questions titled {p(4)}?',
            f'What stored usage count does the tag {p(5)} have?',
            f'Look up the stored usage count of the tag {p(6)}.',
            f'How often is the tag {p(7)} used according to its stored usage count?',
            f'Give the recorded usage count for the tag {p(8)}.',
            f'What score is recorded for questions titled {p(9)}?',
            f'How many views have questions titled {p(10)} received, according to their stored view counts?',
            f'When were questions titled {p(11)} created? Return their creation dates and times.',
            f'Show the scores of questions titled {p(12)}.',
            f'For the tag {p(13)}, return its distinct stored usage count.',
            f'Give the creation date and time of posts titled {p(14)}.',
            f'Which distinct scores belong to posts titled {p(15)}?'
        ]
    else:
        sentences=[
            f'How much reputation does {p(0)} have?',
            f'What date and time was the user account {p(1)} created?',
            f'What creation date and time are recorded for questions titled {p(2)}?',
            f'Find the distinct stored usage count for the tag {p(3)}.',
            f'For posts titled {p(4)}, show the stored view counts.',
            f'On what dates and times were posts titled {p(5)} created?',
            f'Look up the scores of posts titled {p(6)}.',
            f'What distinct view counts do posts titled {p(7)} have?'
        ]
    return dict(zip(ids,sentences))
