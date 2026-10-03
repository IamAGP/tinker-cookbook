"""Protect frozen-data isolation and the new query shapes."""
import json
from .structures import Structure, paths, components
from .v4 import Variant, candidates, load, forbidden, features


def test_all_candidates_respect_frozen_signature_and_component_boundaries():
    structures, _ = load()
    held = {s['signature'] for s in structures if s['split'] == 'heldout_structure'}
    blocked = forbidden(structures)
    for variant in candidates(structures):
        assert variant.signature not in held
        assert not components(variant) & blocked


def test_unordered_lookup_is_semantically_distinct_from_ranked_detail():
    base = Structure(paths()[4], 'detail', 'name')
    variant = Variant(base, 'lookup')
    assert variant.signature != base.signature
    assert json.loads(variant.signature)['ordering'] == 'none'
    assert 'ORDER BY' not in variant.render()
    assert variant.render().endswith('RETURN post_text')


def test_plain_count_and_group_count_use_entities():
    base = Structure(paths()[4], 'detail', 'name')
    assert Variant(base, 'count').render().endswith('RETURN count(n1) AS post_count')
    query = Variant(base, 'group').render(2)
    assert 'n0 AS person, count(n1) AS post_count' in query
    assert 'person.displayName AS user_name, post_count' in query
    assert 'ORDER BY' not in query


def test_ratio_is_multi_aggregate_for_human_mix():
    base = Structure(paths()[4], 'ratio', 'name')
    item = {'rows': [{'percentage': 50}], 'hops': 1}
    structure = {'signature': base.signature, 'mode': 'ratio'}
    result = features(item, structure)
    assert result['aggregation'] == 'more than one aggregate'
    assert result['extras'] == ['ratio']


def test_disjointness_key_ignores_parameter_mapping_order():
    from .v4_batch2 import content_key
    first={'cypher':'RETURN $a + $b','params':{'a':1,'b':2}}
    reordered={'cypher':'RETURN $a + $b','params':{'b':2,'a':1}}
    different={'cypher':'RETURN $a + $b','params':{'a':1,'b':3}}
    assert content_key(first)==content_key(reordered)
    assert content_key(first)!=content_key(different)


def test_second_batch_binding_keeps_first_queue_independent():
    from . import v4_question_authoring as first
    ids=[i['instance_id'] for i in first.QUEUE]
    from . import v4_batch2_question_authoring as second
    assert ids==[i['instance_id'] for i in first.QUEUE]
    assert not set(ids)&{i['instance_id'] for i in second.QUEUE}


def test_scalar_parameter_echo_rejects_text_and_numeric_values():
    from .v4_review_fix import parameter_echo
    assert parameter_echo({'rows':[{'name':'Sirenology'}],'params':{'name':'Sirenology'}})
    assert parameter_echo({'rows':[{'count':1}],'params':{'condition':1.0}})
    assert not parameter_echo({'rows':[{'reputation':37}],'params':{'name':'Sirenology'}})
    assert not parameter_echo({'rows':[{'name':'Sirenology','reputation':37}],'params':{'name':'Sirenology'}})
