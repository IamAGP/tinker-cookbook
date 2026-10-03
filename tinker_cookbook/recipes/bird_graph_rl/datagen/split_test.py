import json
from .split import plan_split, split_instances
from .structures import canonical_path, components, enumerate_structures


def test_split_is_reproducible_and_order_independent():
    structures=enumerate_structures()
    assert plan_split(structures,7)==plan_split(list(reversed(structures)),7)
    assert plan_split(structures,7)!=plan_split(structures,8)


def test_component_holdout_and_tags_are_exact():
    structures=enumerate_structures()
    p=plan_split(structures,42)
    train=[s for s in structures if p.assignments[s.structure_id]=='train']
    held=[s for s in structures if p.assignments[s.structure_id]=='heldout_structure']
    assert not any(p.held_components['extra'] in s.extras for s in train)
    assert not any(canonical_path(s.path)==p.held_components['four_hop_path'] for s in train)
    assert not any(json.dumps([json.loads(s.signature)['aggregation'],s.extras])==p.held_components['aggregation_extras_pairing'] for s in train)
    assert any(s.path.hops==4 and canonical_path(s.path)==p.held_components['four_hop_path'] for s in held)
    seen=frozenset(c for s in train for c in components(s))
    for s in held:
        missing=components(s)-seen
        assert p.novelty[s.structure_id]==('novel_component' if missing else 'novel_combination')
        assert p.unseen_components[s.structure_id]==sorted(missing)
    assert set(p.novelty.values())=={'novel_component','novel_combination'}
    for hop in range(5):
        group=[s for s in structures if s.path.hops==hop]
        forced=[s for s in group if p.held_components['extra'] in s.extras or canonical_path(s.path)==p.held_components['four_hop_path'] or json.dumps([json.loads(s.signature)['aggregation'],s.extras])==p.held_components['aggregation_extras_pairing']]
        assert sum(p.assignments[s.structure_id]=='heldout_structure' for s in group)==max(round(len(group)*.2),len(forced))


def test_instance_holdout_is_disjoint_reproducible():
    ids=[f'i_{i}' for i in range(12)]
    a=split_instances(ids,'train',7)
    assert a==split_instances(list(reversed(ids)),'train',7)
    assert list(a.values()).count('heldout_instance')==2
    assert set(split_instances(ids,'heldout_structure',7).values())=={'heldout_structure'}
