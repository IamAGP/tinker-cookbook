from dataclasses import replace
import json

from .structures import Path, Structure, canonical_signature, enumerate_structures, paths


def test_signatures_are_stable_and_unique():
    a,b = enumerate_structures(),enumerate_structures()
    assert len(a) >= 150
    assert [s.signature for s in a] == [s.signature for s in b]
    assert len({s.structure_id for s in a}) == len(a)
    assert len({s.signature for s in a}) == len(a)
    assert all(s.structure_id == replace(s).structure_id for s in a)
    assert {s.path.hops for s in a} == set(range(5))
    assert sum(s.path.hops <= 1 for s in a)/len(a) <= .35


def test_filter_multiset_and_extras_set():
    path = Path(('User',))
    a = canonical_signature(path,['id','year'],'count','none','none',('negation','existence'))
    b = canonical_signature(path,['year','id'],'count','none','none',('existence','negation','existence'))
    assert a == b
    assert a != canonical_signature(path,['id','id','year'],'count','none','none',('negation','existence'))


def test_direction_and_aggregation_and_ordering_change_signature():
    path = Path(('Post','Post'),((0,'LINKS_TO',1),))
    reversed_path = Path(('Post','Post'),((1,'LINKS_TO',0),))
    assert Structure(path,'sum').signature != Structure(reversed_path,'sum').signature
    assert Structure(path,'sum').signature != Structure(path,'avg').signature
    assert Structure(path,'detail').signature != Structure(path,'top').signature
    assert Structure(path,'argmax').signature != Structure(path,'top').signature
    assert Structure(path,'argmax').signature != Structure(path,'bottom').signature


def test_parameter_values_do_not_enter_signatures():
    s = enumerate_structures()[0]
    assert '$' in s.render()
    assert set(json.loads(s.signature)) == {'path','filters','aggregation','grouping','ordering','extras'}
    assert 'params' not in json.loads(s.signature)


def test_paths_are_schema_valid():
    edges = {('User','OWNS','Post'),('User','WROTE','Comment'),('User','MADE','PostHistory'),
             ('User','CAST','Vote'),('User','EARNED','Badge'),('Answer','ANSWERS','Question'),
             ('Question','ACCEPTED','Answer'),('Post','LINKS_TO','Post'),('Post','TAGGED','Tag'),
             ('Comment','ON_POST','Post'),('Vote','ON_POST','Post'),('PostHistory','REVISES','Post'),
             ('Tag','HAS_WIKI','Post')}
    def matches(actual,expected):
        return actual == expected or actual in ('Answer','Question') and expected == 'Post' or actual == 'Post' and expected in ('Answer','Question')
    for path in paths():
        for a,rel,b in path.edges:
            assert any(rel == r and matches(path.labels[a],src) and matches(path.labels[b],dst)
                       for src,r,dst in edges)
