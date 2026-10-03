from dataclasses import replace
import json
from .structures import Path, Structure, canonical_signature, enumerate_structures, chain


def sig(path, filters=(), aggregation=('sum','Post'), grouping='none', ordering='none', extras=()):
    return canonical_signature(path,list(filters),aggregation,grouping,ordering,extras)


def test_signatures_stable_unique_and_parameter_free():
    a,b=enumerate_structures(),enumerate_structures()
    assert [s.signature for s in a] == [s.signature for s in b]
    assert len({s.structure_id for s in a}) == len(a)
    assert all(s.structure_id == replace(s).structure_id for s in a)
    assert {s.path.hops for s in a} == set(range(5))
    assert all(set(json.loads(s.signature)) == {'path','filters','aggregation','grouping','ordering','extras'} for s in a)


def test_uniform_label_granularity():
    path=Path(('User','Post'),((0,'OWNS',1),))
    s=Structure(path,'sum')
    parsed=json.loads(s.signature)
    assert parsed['aggregation'] == ['sum','Post']
    assert all(len(f)==2 and f[0] in ('User','Post') for f in parsed['filters'])
    assert 'score' not in s.signature and 'postId' not in s.signature
    assert Structure(path,'sum',metric_property='score').signature == Structure(path,'sum',metric_property='viewCount').signature
    assert sig(path,[('Post','year/date range')]) != sig(path,[('User','year/date range')])
    # Different measured properties cannot enter this signature API.
    assert sig(path,aggregation=('sum','Post')) == sig(path,aggregation=('sum','Post'))
    assert sig(path,aggregation=('sum','Post')) != sig(path,aggregation=('avg','Post'))


def test_branch_order_and_variable_names_are_canonical():
    a=Path(('User','Post','Badge'),((0,'OWNS',1),(0,'EARNED',2)))
    b=Path(('Badge','User','Post'),((1,'EARNED',0),(1,'OWNS',2)))
    assert sig(a) == sig(b)
    assert sig(a) == sig(Path(a.labels,tuple(reversed(a.edges))))


def test_schema_direction_independent_of_traversal():
    assert sig(chain(('User','Post'),'OWNS')) == sig(chain(('Post','User'),'<OWNS'))
    assert sig(chain(('Post','Post'),'LINKS_TO')) != sig(Path(('Post','Post'),()))


def test_subtypes_equal_explicit_label_filters():
    for subtype in ('Question','Answer'):
        assert sig(Path((subtype,)),aggregation=('sum',subtype)) == sig(
            Path(('Post',)),[('Post','label test:'+subtype)])
    assert Structure(Path(('Question',)),'distinct').signature == Structure(Path(('Post',)),'label').signature


def test_multiset_filters_and_set_extras():
    p=Path(('User',))
    a=sig(p,[('User','id'),('User','year')],extras=('negation','existence'))
    b=sig(p,[('User','year'),('User','id')],extras=('existence','negation','existence'))
    assert a==b
    assert a!=sig(p,[('User','id'),('User','id'),('User','year')],extras=('negation','existence'))
