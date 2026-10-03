"""Schema-valid, parameter-free query structures for stage A."""
from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
import hashlib
import json

JSONScalar = str | int | float | bool | None

# Identity, numeric measurement, optional property, human-readable entity.
PROPERTIES = {
    'User': ('userId', 'reputation', 'location', 'member'),
    'Post': ('postId', 'score', 'title', 'post'),
    'Question': ('postId', 'score', 'closedDate', 'question'),
    'Answer': ('postId', 'score', 'lastEditDate', 'answer'),
    'Comment': ('commentId', 'score', 'userDisplayName', 'comment'),
    'Vote': ('voteId', 'voteTypeId', 'bountyAmount', 'vote'),
    'PostHistory': ('postHistoryId', 'postHistoryTypeId', 'comment', 'revision'),
    'Tag': ('tagId', 'count', 'tagName', 'tag'),
    'Badge': ('name', '', 'name', 'badge'),
}

@dataclass(frozen=True)
class Path:
    labels: tuple[str, ...]
    edges: tuple[tuple[int, str, int], ...] = ()

    @property
    def hops(self) -> int:
        return len(self.edges)

    @property
    def pattern(self) -> str:
        if not self.edges:
            return f'(n0:{self.labels[0]})'
        # Repeated variables enforce joins, including shared roots in branches.
        return ', '.join(
            f'(n{a}:{self.labels[a]})-[:{rel}]->(n{b}:{self.labels[b]})'
            for a, rel, b in self.edges
        )

    @property
    def endpoint(self) -> str:
        return f'n{len(self.labels)-1}'

    @property
    def identity(self) -> str:
        return f'{self.endpoint}.{PROPERTIES[self.labels[-1]][0]}'

    @property
    def measure(self) -> str:
        return f'{self.endpoint}.{PROPERTIES[self.labels[-1]][1]}'


def chain(labels: tuple[str, ...], *edges: str) -> Path:
    return Path(labels, tuple((i+1, rel[1:], i) if rel.startswith('<') else
                              (i, rel, i+1) for i, rel in enumerate(edges)))


def paths() -> list[Path]:
    return [
        *(Path((label,)) for label in ('User', 'Post', 'Question', 'Tag')),
        chain(('User','Post'), 'OWNS'),
        chain(('User','Comment'), 'WROTE'),
        chain(('Answer','Question'), 'ANSWERS'),
        chain(('Post','Post'), 'LINKS_TO'),
        chain(('Question','Answer'), 'ACCEPTED'),
        chain(('Tag','Post'), 'HAS_WIKI'),
        chain(('User','Comment','Post'), 'WROTE','ON_POST'),
        chain(('User','PostHistory','Post'), 'MADE','REVISES'),
        chain(('User','Vote','Post'), 'CAST','ON_POST'),
        chain(('User','Post','Tag'), 'OWNS','TAGGED'),
        chain(('Post','Post','User'), 'LINKS_TO','<OWNS'),
        chain(('Question','Answer','User'), 'ACCEPTED','<OWNS'),
        chain(('User','Badge','User'), 'EARNED','<EARNED'),
        chain(('User','Post','Post','User'), 'OWNS','LINKS_TO','<OWNS'),
        chain(('User','Comment','Post','Tag'), 'WROTE','ON_POST','TAGGED'),
        chain(('User','PostHistory','Post','Tag'), 'MADE','REVISES','TAGGED'),
        chain(('Question','Answer','User','Comment'), 'ACCEPTED','<OWNS','WROTE'),
        chain(('Post','Post','Post','User'), 'LINKS_TO','LINKS_TO','<OWNS'),
        chain(('User','Answer','Question','User'), 'OWNS','ANSWERS','<OWNS'),
        chain(('User','Post','Post','User','Comment'), 'OWNS','LINKS_TO','<OWNS','WROTE'),
        chain(('User','Comment','Post','Post','User'), 'WROTE','ON_POST','LINKS_TO','<OWNS'),
        chain(('User','PostHistory','Post','Post','User'), 'MADE','REVISES','LINKS_TO','<OWNS'),
        chain(('Question','Answer','User','Post','Tag'), 'ACCEPTED','<OWNS','OWNS','TAGGED'),
        chain(('Post','Post','User','Comment','Post'), 'LINKS_TO','<OWNS','WROTE','ON_POST'),
        chain(('User','Answer','Question','Answer','User'), 'OWNS','ANSWERS','ACCEPTED','<OWNS'),
        # Branches count total edges, rather than longest arm.
        Path(('User','Post','Badge'), ((0,'OWNS',1),(0,'EARNED',2))),
        Path(('User','Comment','Badge','Post'), ((0,'WROTE',1),(0,'EARNED',2),(1,'ON_POST',3))),
        Path(('User','Post','Badge','Post','User'),
             ((0,'OWNS',1),(0,'EARNED',2),(1,'LINKS_TO',3),(4,'OWNS',3))),
    ]

@dataclass(frozen=True)
class Structure:
    path: Path
    mode: str

    @property
    def endpoint(self) -> str:
        # The two-arm User/Post/Badge branch measures its Post arm.
        return 'n1' if self.path.labels[-1] == 'Badge' else self.path.endpoint

    @property
    def label(self) -> str:
        return self.path.labels[int(self.endpoint[1:])]

    @property
    def identity(self) -> str:
        return f'{self.endpoint}.{PROPERTIES[self.label][0]}'

    @property
    def measure(self) -> str:
        return f'{self.endpoint}.{PROPERTIES[self.label][1]}'

    @property
    def aggregation(self) -> str:
        return {'detail':'none', 'distinct':'count distinct', 'group':'count',
                'top':'none', 'bottom':'none', 'argmax':'none', 'ratio':'count', 'difference':'sum',
                'having':'count', 'exists':'count', 'negation':'count',
                'year':'avg', 'null':'sum', 'not_null':'avg', 'contains':'count',
                'starts':'count', 'label':'count', 'named':'sum', 'comparison':'sum'}.get(self.mode,self.mode)

    @property
    def extras(self) -> tuple[str, ...]:
        return {'exists':('existence',), 'negation':('existence','negation'),
                'ratio':('ratio/percentage',), 'difference':('difference of two aggregates',),
                'comparison':('comparison between two named entities',),
                'having':('HAVING-style post-filter',)}.get(self.mode,())

    @cached_property
    def signature(self) -> str:
        filters = ['numeric range' if self.path.hops == 0 else 'equality on id']
        if self.mode in ('named','comparison'):
            filters = ['equality on name']
        extra_filter = {'year':'year/date range', 'null':'IS NULL', 'not_null':'IS NOT NULL',
                        'contains':'string CONTAINS','starts':'string STARTS WITH',
                        'label':'label test (Question)'}.get(self.mode)
        if extra_filter:
            filters.append(extra_filter)
        return canonical_signature(self.path, filters, self.aggregation,
                                   self.identity if self.mode in ('group','having') else 'none',
                                   {'detail':'order-by','group':'order-by','having':'order-by',
                                    'top':'top-k','bottom':'argmin','argmax':'argmax'}.get(self.mode,'none'),
                                   self.extras)

    @cached_property
    def structure_id(self) -> str:
        return 's_' + hashlib.sha256(self.signature.encode()).hexdigest()[:16]

    def render(self, probe: bool = False) -> str:
        p = self.path
        root_key, root_metric, _, _ = PROPERTIES[p.labels[0]]
        predicate = f'n0.{root_key} = $anchor' if p.hops else f'n0.{root_metric} >= $lower AND n0.{root_metric} <= $upper'
        if self.mode == 'named':
            predicate = 'n0.displayName = $name'
        if self.mode == 'comparison':
            predicate = 'n0.displayName IN [$name, $other_name]'
        m, ident, end = self.measure, self.identity, self.endpoint
        if self.mode == 'year':
            predicate += f' AND {end}.creationDate.year >= $year AND {end}.creationDate.year <= $end_year'
        if self.mode in ('null','not_null'):
            predicate += f' AND {end}.{PROPERTIES[self.label][2]} IS ' + ('NOT NULL' if self.mode == 'not_null' else 'NULL')
        if self.mode in ('contains','starts'):
            text_key = 'displayName' if self.label == 'User' else 'tagName' if self.label == 'Tag' else 'title'
            predicate += f' AND {end}.{text_key} ' + ('CONTAINS' if self.mode == 'contains' else 'STARTS WITH') + ' $text'
        if self.mode == 'label':
            predicate += f' AND {end}:Question'
        if self.mode in ('exists','negation'):
            # Explicit label-qualified ON_POST is crucial: votes also use that type.
            predicate += f' AND ' + ('NOT ' if self.mode == 'negation' else '') + f'EXISTS {{ MATCH (:Comment)-[:ON_POST]->({end}) }}'
        base = f'CYPHER 25 MATCH {p.pattern} WHERE {predicate} '
        if self.mode == 'detail':
            return base + f'RETURN DISTINCT {ident} AS entity_id, {m} AS value ORDER BY entity_id'
        if self.mode in ('top','bottom','argmax'):
            direction = 'DESC' if self.mode in ('top','argmax') else 'ASC'
            # Secondary ID establishes total order; probe still tests the primary key.
            return base + f'WITH DISTINCT {ident} AS entity_id, {m} AS value WHERE value IS NOT NULL RETURN entity_id, value ORDER BY value {direction}, entity_id ASC LIMIT ' + ('$probe_k' if probe else '$k')
        if self.mode in ('group','having'):
            having = ' WHERE value >= $threshold' if self.mode == 'having' else ''
            return base + f'WITH {ident} AS entity_id, count(*) AS value{having} RETURN entity_id, value ORDER BY entity_id'
        if self.mode == 'ratio':
            return base + f'RETURN CASE WHEN count(*) = 0 THEN null ELSE 100.0 * sum(CASE WHEN {m} > 0 THEN 1 ELSE 0 END) / count(*) END AS percentage'
        if self.mode == 'difference':
            return base + f'RETURN sum({m}) - sum(abs({m})) AS difference'
        if self.mode == 'comparison':
            return base + f'RETURN sum(CASE WHEN n0.displayName = $name THEN {m} ELSE 0 END) - sum(CASE WHEN n0.displayName = $other_name THEN {m} ELSE 0 END) AS difference'
        expression = f'count(DISTINCT {ident})' if self.mode == 'distinct' else 'count(*)' if self.aggregation == 'count' else f'{self.aggregation}({m})'
        return base + f'RETURN {expression} AS value'


def canonical_signature(path: Path, filters: list[str], aggregation: str,
                        grouping: str, ordering: str, extras: tuple[str, ...]) -> str:
    """Filters form a multiset; extras a set; ordered paths retain orientation."""
    return json.dumps({'path':{'labels':path.labels,'edges':path.edges},
                       'filters':sorted(filters),'aggregation':aggregation,
                       'grouping':grouping,'ordering':ordering,'extras':sorted(set(extras))},
                      sort_keys=True,separators=(',',':'))


def enumerate_structures() -> list[Structure]:
    result: dict[str, Structure] = {}
    for path in paths():
        modes = ['detail','count','distinct','sum','avg','min','max','group','top','bottom','argmax']
        if path.hops == 0:
            modes = ['count','sum','avg','top','argmax']
        if path.hops >= 2:
            modes += ['ratio','difference','having']
        label = 'Post' if path.labels[-1] == 'Badge' else path.labels[-1]
        if label in ('Post','Question','Answer') and path.hops >= 2:
            endpoint_index = 1 if path.labels[-1] == 'Badge' else len(path.labels)-1
            already_has_comment = any(rel == 'ON_POST' and path.labels[a] == 'Comment' and b == endpoint_index for a,rel,b in path.edges)
            if not already_has_comment:
                modes += ['exists','negation']
            if label == 'Post':
                modes += ['label']
        if label not in ('Tag','Badge') and path.hops >= 2:
            modes += ['year','null','not_null']
        if label in ('User','Post','Question','Tag') and path.hops >= 2:
            modes += ['contains','starts']
        if path.labels[0] == 'User' and path.hops >= 2:
            modes += ['named','comparison']
        for mode in modes:
            structure = Structure(path,mode)
            # Mode synonyms yielding equal six-tuples are intentionally collapsed.
            result.setdefault(structure.signature,structure)
    return sorted(result.values(),key=lambda s:s.structure_id)
