from .split import split_instances, split_structures
from .structures import enumerate_structures


def test_structure_split_is_reproducible_and_order_independent():
    structures = enumerate_structures()
    a = split_structures(structures,7)
    assert a == split_structures(list(reversed(structures)),7)
    assert a != split_structures(structures,8)
    for hops in range(5):
        ids = [s.structure_id for s in structures if s.path.hops == hops]
        assert abs(sum(a[i] == 'heldout_structure' for i in ids)/len(ids)-.2) <= 1/len(ids)


def test_structure_and_parameter_holdouts_are_disjoint():
    structures = enumerate_structures()
    assignments = split_structures(structures,42)
    by_split = {'train':set(),'heldout_structure':set(),'heldout_instance':set()}
    for structure in structures:
        ids = [f'{structure.structure_id}:{i}' for i in range(12)]
        split = split_instances(ids,assignments[structure.structure_id],42)
        assert split == split_instances(list(reversed(ids)),assignments[structure.structure_id],42)
        assert set(split) == set(ids)
        for iid,part in split.items():
            by_split[part].add(structure.structure_id)
        if assignments[structure.structure_id] == 'train':
            assert list(split.values()).count('heldout_instance') == 2
            assert list(split.values()).count('train') == 10
    assert not by_split['train'] & by_split['heldout_structure']
    assert by_split['train'] == by_split['heldout_instance']
