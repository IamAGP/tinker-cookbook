from .generate import boundary_tie, canonical_rows, parameter_sets, rejection
from .structures import JSONScalar, Path, Structure


def test_acceptance_rules():
    assert rejection([],1) == 'row_count'
    assert rejection([{'x':1}]*201,1) == 'row_count'
    assert rejection([{'x':None}],1) == 'all_null'
    assert rejection([{'x':0}],5001) == 'runtime_over_5s'
    assert rejection([{'x':0,'y':None}],5000) is None


def test_boundary_uses_primary_sort_key_even_with_identity_tiebreak():
    assert boundary_tie([{'value':9},{'value':8},{'value':8}],2)
    assert not boundary_tie([{'value':9},{'value':8},{'value':7}],2)
    assert not boundary_tie([{'value':9}],1)


def test_multiset_comparison_does_not_lose_duplicates_or_columns():
    assert canonical_rows([{'a':1},{'a':2}]) == canonical_rows([{'a':2},{'a':1}])
    assert canonical_rows([{'a':1},{'a':1}]) != canonical_rows([{'a':1}])
    assert canonical_rows([{'a':1}]) != canonical_rows([{'b':1}])


def test_seeded_parameters_are_distinct():
    s = Structure(Path(('User','Post'),((0,'OWNS',1),)),'top')
    pool = [{'anchor':i,'metric':i} for i in range(100)]
    a = parameter_sets(s,pool,{},7,96)
    assert a == parameter_sets(s,pool,{},7,96)
    assert a != parameter_sets(s,pool,{},8,96)
    assert len({str(p) for p in a}) == len(a)


def test_missing_or_ambiguous_names_cannot_be_sampled():
    s = Structure(Path(('User','Post'),((0,'OWNS',1),)),'named')
    assert parameter_sets(s,[{'anchor':1,'metric':1}],{},7,96) == []
    assert parameter_sets(s,[{'anchor':1,'metric':1}],{1:'Unique'},7,96) == [{'name':'Unique'}]


def test_nontriviality_search_replaces_constant_answer_in_capped_group():
    from collections import Counter
    from .generate import Params, Rows, ReadGraph, generate_structure
    class FakeGraph(ReadGraph):
        def __init__(self) -> None:
            pass
        def execute(self, cypher: str, params: Params | dict[str,list[JSONScalar]] | None = None,
                    cap: int | None = 201, timeout: float = 5.0) -> tuple[Rows,float]:
            assert params is not None
            return [{'value':int(params['anchor'] == 12)}],1.0
    s = Structure(Path(('User','Post'),((0,'OWNS',1),)),'count')
    rejects = Counter()
    kept = generate_structure(FakeGraph(),s,[{'anchor':i} for i in range(13)],set(),rejects)
    assert len(kept) == 12
    assert {i.rows[0]['value'] for i in kept} == {0,1}
    assert not rejects


def test_constant_structure_is_dropped_and_all_observations_counted():
    from collections import Counter
    from .generate import Params, Rows, ReadGraph, generate_structure
    class FakeGraph(ReadGraph):
        def __init__(self) -> None:
            pass
        def execute(self, cypher: str, params: Params | dict[str,list[JSONScalar]] | None = None,
                    cap: int | None = 201, timeout: float = 5.0) -> tuple[Rows,float]:
            return [{'value':0}],1.0
    s = Structure(Path(('User','Post'),((0,'OWNS',1),)),'count')
    rejects = Counter()
    assert not generate_structure(FakeGraph(),s,[{'anchor':i} for i in range(96)],set(),rejects)
    assert rejects['trivial_constant_answer'] == 96


def test_ranges_are_sampled_from_observed_values():
    s = Structure(Path(('User',)),'avg','range')
    pool = [{'anchor':i,'metric':i*7} for i in range(10)]
    sampled = parameter_sets(s,pool,{},7,96)
    observed = {row['metric'] for row in pool}
    assert all(p['lower'] in observed and p['upper'] in observed and p['lower'] <= p['upper'] for p in sampled)
    s = Structure(Path(('User','Post'),((0,'OWNS',1),)),'year')
    sampled = parameter_sets(s,[{'anchor':1,'metric':1,'years':'2010|2012'}],{},7,96)
    assert all(p['year'] in (2010,2012) and p['end_year'] in (2010,2012) and p['year'] <= p['end_year'] for p in sampled)


def test_read_guard_blocks_mutations_before_driver_access():
    import pytest
    from .generate import ReadGraph
    graph = ReadGraph.__new__(ReadGraph)
    for query in ('CREATE (n:User)','MATCH (n) DELETE n','CALL db.labels()','LOAD CSV FROM $url AS row RETURN row'):
        with pytest.raises(ValueError,match='non-read clause blocked'):
            graph.execute(query)
