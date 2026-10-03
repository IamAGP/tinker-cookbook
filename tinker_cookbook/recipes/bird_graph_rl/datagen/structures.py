"""Schema-valid, parameter-free query structures for stage A."""
from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property, lru_cache
import hashlib
import json
from itertools import permutations

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

# Ordinary meanings, indexed only by schema-valid generated patterns.
DESCRIPTIONS = (
 'users', 'posts', 'questions', 'tags', 'posts authored by the selected users',
 'comments written by the selected users', 'questions to which the selected answers respond',
 'posts linked to from the selected posts', 'accepted answers to the selected questions',
 'wiki posts for the selected tags', 'posts commented on by the selected users',
 'posts with revision activity by the selected users', 'posts voted on by the selected users',
 'tags on posts authored by the selected users', 'authors of posts linked to from the selected posts',
 'authors of accepted answers to the selected questions', 'users with badges in common with the selected users',
 'authors of posts linked to from posts by the selected users',
 'tags on posts commented on by the selected users', 'tags on posts with revision activity by the selected users',
 'comments by authors of accepted answers to the selected questions',
 'authors of posts reached by following two successive post links from the selected posts',
 'authors of questions answered by the selected users',
 'comments by authors of posts linked to from posts by the selected users',
 'authors of posts linked to from posts commented on by the selected users',
 'authors of posts linked to from posts with revision activity by the selected users',
 'tags on posts by authors of accepted answers to the selected questions',
 'posts commented on by authors of posts linked to from the selected posts',
 'authors of accepted answers to questions answered by the selected users',
 'posts authored by holders of the selected badge',
 'posts commented on by holders of the selected badge',
 'authors of posts linked to from posts by holders of the selected badge',
)

@dataclass(frozen=True)
class Structure:
    path: Path
    mode: str
    anchor: str = 'id'
    metric_property: str | None = None

    @property
    def endpoint(self) -> str:
        return 'n1' if self.path.labels[-1] == 'Badge' else self.path.endpoint

    @property
    def label(self) -> str:
        return self.path.labels[int(self.endpoint[1:])]

    @property
    def identity(self) -> str:
        return f'{self.endpoint}.{PROPERTIES[self.label][0]}'

    @property
    def measure(self) -> str:
        return f'{self.endpoint}.{self.metric_property or PROPERTIES[self.label][1]}'

    @property
    def metric(self) -> str:
        return self.metric_property or PROPERTIES[self.label][1]

    @property
    def display(self) -> tuple[str,str]:
        label=self.label; end=self.endpoint
        if label=='User': return f'{end}.displayName','user_name'
        if label=='Tag': return f'{end}.tagName','tag_name'
        if label=='Comment': return f'left({end}.text,120)','comment_text'
        if label=='Answer': return f'left({end}.body,120)','answer_text'
        return f'coalesce({end}.title,left({end}.body,120))','post_text'

    @property
    def previous(self) -> int:
        end=int(self.endpoint[1:])
        return next(a if b==end else b for a,rel,b in reversed(self.path.edges) if a==end or b==end)

    @property
    def aggregation(self) -> str:
        return {'detail':'none','top':'none','bottom':'none','argmax':'none',
          'distinct':'count distinct','entity_group':'count distinct','entity_having':'count distinct',
          'ratio':'count distinct','exists':'count distinct','negation':'count distinct',
          'year':'avg','null':'sum','not_null':'avg','contains':'count distinct','starts':'count distinct',
          'label':'count distinct','named':'sum','comparison':'sum','group':'count','having':'count','difference':'sum'}.get(self.mode,self.mode)

    @property
    def extras(self) -> tuple[str,...]:
        return {'exists':('existence',),'negation':('existence','negation'),
          'ratio':('ratio/percentage',),'difference':('difference of two aggregates',),
          'comparison':('comparison between two named entities',),
          'having':('HAVING-style post-filter',),'entity_having':('HAVING-style post-filter',)}.get(self.mode,())

    @property
    def anchor_label(self) -> str:
        return 'Badge' if self.anchor=='badge' else self.path.labels[0]

    @cached_property
    def signature(self) -> str:
        anchor_kind={'id':'equality on id','name':'equality on name','title':'equality on name',
                     'badge':'equality on name','date':'year/date range','range':'numeric range'}[self.anchor]
        if self.mode in ('named','comparison'): anchor_kind='equality on name'
        filters=[(self.anchor_label,anchor_kind)]
        extra={'year':'year/date range','null':'IS NULL','not_null':'IS NOT NULL',
               'contains':'string CONTAINS','starts':'string STARTS WITH','label':'label test:Question'}.get(self.mode)
        if extra: filters.append((self.label,extra))
        target=self.path.labels[self.previous] if self.mode in ('entity_group','entity_having') else self.label
        grouping=self.label if self.mode in ('group','having','entity_group','entity_having') else 'none'
        ordering={'detail':'order-by','group':'order-by','having':'order-by','entity_group':'order-by',
                  'entity_having':'order-by','top':'top-k','bottom':'argmin','argmax':'argmax'}.get(self.mode,'none')
        return canonical_signature(self.path,filters,(self.aggregation,target),grouping,ordering,self.extras)

    @cached_property
    def structure_id(self) -> str:
        return 's_'+hashlib.sha256(self.signature.encode()).hexdigest()[:16]

    @property
    def description(self) -> str:
        description=DESCRIPTIONS[paths().index(self.path)]
        if self.anchor!='badge': description=description.replace('holders of the selected badge','the selected users who have badges')
        return description

    @property
    def intent(self) -> str:
        description=self.description
        metric={'score':'score','reputation':'reputation','count':'stored tag usage count','viewCount':'view count'}.get(self.metric,self.metric)
        if self.mode in ('entity_group','entity_having'):
            subject=PROPERTIES[self.path.labels[self.previous]][3]
            return f'List {description} and the number of distinct associated {subject}s'+(' meeting a minimum count.' if self.mode=='entity_having' else '.')
        if self.mode=='comparison': return f'Compare the total {metric} of {description} for two named users.'
        if self.mode=='ratio': return f'What percentage of {description} have positive {metric}?'
        if self.aggregation=='none': return f'List {description} with their {metric}'+(' ranked by '+metric+'.' if self.mode in ('top','bottom','argmax') else '.')
        if self.aggregation=='count distinct': return f'How many distinct {description} satisfy the stated conditions?'
        return f'What is the '+{'avg':'average','sum':'total','min':'minimum','max':'maximum'}.get(self.aggregation,self.aggregation)+f' {metric} of {description} under the stated conditions?'

    @property
    def sort_column(self) -> str:
        return 'stored_tag_count' if self.metric=='count' else self.metric

    def render(self, probe: bool=False) -> str:
        root_key,root_metric,_,_=PROPERTIES[self.path.labels[0]]
        predicate=f'n0.{root_key} = $anchor'
        if self.anchor=='range': predicate=f'n0.{root_metric} >= $lower AND n0.{root_metric} <= $upper'
        if self.anchor=='name': predicate='n0.'+('displayName' if self.path.labels[0]=='User' else 'tagName')+' = $name'
        if self.anchor=='title': predicate='n0.title = $title'
        if self.anchor=='badge': predicate='n2.name = $badge'
        if self.anchor=='date': predicate="n0.creationDate >= localdatetime($date + 'T00:00:00') AND n0.creationDate < localdatetime($date + 'T00:00:00') + duration({days:1})"
        if self.mode=='named': predicate='n0.displayName = $name'
        if self.mode=='comparison': predicate='n0.displayName IN [$name,$other_name]'
        end=self.endpoint; m=self.measure; ident=self.identity
        if self.mode=='year': predicate+=f' AND {end}.creationDate.year >= $year AND {end}.creationDate.year <= $end_year'
        if self.mode in ('null','not_null'): predicate+=f' AND {end}.{PROPERTIES[self.label][2]} IS '+('NOT NULL' if self.mode=='not_null' else 'NULL')
        if self.mode in ('contains','starts'):
            field='displayName' if self.label=='User' else 'tagName' if self.label=='Tag' else 'title'
            predicate+=f' AND {end}.{field} '+('CONTAINS' if self.mode=='contains' else 'STARTS WITH')+' $text'
        if self.mode=='label': predicate+=f' AND {end}:Question'
        if self.mode in ('exists','negation'):
            predicate+=' AND '+('NOT ' if self.mode=='negation' else '')+f'EXISTS {{ MATCH (:Comment)-[:ON_POST]->({end}) }}'
        base=f'CYPHER 25 MATCH REPEATABLE ELEMENTS {self.path.pattern} WHERE {predicate} '
        display,column=self.display
        metric_column=self.sort_column
        if self.mode in ('detail','top','bottom','argmax'):
            base+=f'WITH DISTINCT {ident} AS identity, {display} AS {column}, {m} AS {metric_column} '
            if self.mode!='detail': base+=f'WHERE {metric_column} IS NOT NULL '
            base+=f'RETURN {column}, {metric_column} '
            if self.mode=='detail': return base+'ORDER BY identity'
            direction='ASC' if self.mode=='bottom' else 'DESC'
            return base+f'ORDER BY {metric_column} {direction}, identity ASC LIMIT '+('$probe_k' if probe else '$k')
        if self.mode in ('entity_group','entity_having'):
            previous=f'n{self.previous}.{PROPERTIES[self.path.labels[self.previous]][0]}'
            base+=f'WITH {ident} AS identity, {display} AS {column}, count(DISTINCT {previous}) AS associated_count '
            if self.mode=='entity_having': base+='WHERE associated_count >= $threshold '
            return base+f'RETURN {column}, associated_count ORDER BY identity'
        if self.mode=='comparison':
            return base+f'WITH DISTINCT n0.displayName AS person, {ident} AS identity, {m} AS measurement RETURN sum(CASE WHEN person=$name THEN measurement ELSE 0 END)-sum(CASE WHEN person=$other_name THEN measurement ELSE 0 END) AS {self.metric}_difference'
        # Deduplicate entities BEFORE aggregation, never SUM(DISTINCT score).
        base+=f'WITH DISTINCT {ident} AS identity, {m} AS measurement '
        if self.mode=='ratio': return base+'RETURN CASE WHEN count(*)=0 THEN null ELSE 100.0*sum(CASE WHEN measurement>0 THEN 1 ELSE 0 END)/count(*) END AS positive_percentage'
        if self.aggregation=='count distinct': return base+f'RETURN count(*) AS {self.label.lower()}_count'
        alias={'sum':'total','avg':'average','min':'minimum','max':'maximum'}.get(self.aggregation,self.aggregation)+'_'+metric_column
        return base+f'RETURN {self.aggregation}(measurement) AS {alias}'


def normal_label(label: str) -> str:
    return 'Post' if label in ('Question','Answer') else label


@lru_cache(maxsize=None)
def canonical_path(path: Path) -> str:
    """Variable-renaming invariant directed graph; branch order never matters."""
    labels = tuple(normal_label(label) for label in path.labels)
    forms = []
    for order in permutations(range(len(labels))):
        positions = {old:new for new,old in enumerate(order)}
        form = {'labels':tuple(labels[i] for i in order),
                'edges':sorted((positions[a],rel,positions[b]) for a,rel,b in path.edges)}
        forms.append(json.dumps(form,sort_keys=True,separators=(',',':')))
    return min(forms)


def canonical_signature(path: Path, filters: list[tuple[str,str]],
                        aggregation: tuple[str,str], grouping: str,
                        ordering: str, extras: tuple[str, ...]) -> str:
    normalized_filters = [(normal_label(label),kind) for label,kind in filters]
    normalized_filters += [('Post','label test:'+label) for label in path.labels
                           if label in ('Question','Answer')]
    return json.dumps({'path':json.loads(canonical_path(path)),
        'filters':sorted(normalized_filters),
        'aggregation':(aggregation[0],normal_label(aggregation[1])),
        'grouping':normal_label(grouping),'ordering':ordering,
        'extras':sorted(set(extras))},sort_keys=True,separators=(',',':'))


def components(structure: Structure) -> frozenset[str]:
    sig = json.loads(structure.signature)
    values = [json.dumps([key,sig[key]],sort_keys=True) for key in
              ('path','aggregation','grouping','ordering')]
    values += [json.dumps(['filter',item]) for item in sig['filters']]
    values += [json.dumps(['extra',item]) for item in sig['extras']]
    values.append(json.dumps(['aggregation_extras',sig['aggregation'],sig['extras']]))
    return frozenset(values)


def candidate_structures() -> list[Structure]:
    result: dict[str, Structure] = {}
    for path in paths():
        modes = ['detail','count','distinct','sum','avg','min','max','group','top','bottom','argmax']
        if path.hops == 0:
            modes = ['count','sum','avg','top','argmax']
        if path.hops >= 2:
            modes += ['ratio','difference','having','entity_group','entity_having']
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
            if path.hops==0:
                anchor='range'
            elif mode in ('named','comparison'):
                anchor='name'
            elif path.labels[-1]=='Badge' or (len(path.labels)>2 and path.labels[2]=='Badge'):
                anchor='badge'
            else:
                choice=int(hashlib.sha256((path.pattern+mode).encode()).hexdigest()[:8],16)%10
                root=path.labels[0]
                anchor='id' if choice<2 else ('date' if choice<4 or root=='Answer' else 'name' if root in ('User','Tag') else 'title')
                if root=='Tag' and anchor=='date': anchor='name'
            structure = Structure(path,mode,anchor)
            # Mode synonyms yielding equal six-tuples are intentionally collapsed.
            result.setdefault(structure.signature,structure)
    return sorted(result.values(),key=lambda s:s.structure_id)


def enumerate_structures() -> list[Structure]:
    from .naturalness import decide
    return [s for s in candidate_structures() if decide(s.mode).keep]
