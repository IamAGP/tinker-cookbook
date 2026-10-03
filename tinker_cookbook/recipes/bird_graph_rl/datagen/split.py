"""Seeded, hop-stratified structure split and reserved instance split."""
from __future__ import annotations
from collections import defaultdict
import random
from .structures import Structure


def split_structures(structures: list[Structure], seed: int) -> dict[str,str]:
    strata: dict[int,list[str]] = defaultdict(list)
    for structure in structures:
        strata[structure.path.hops].append(structure.structure_id)
    rng = random.Random(seed)
    assignments: dict[str,str] = {}
    for hops in sorted(strata):
        ids = sorted(set(strata[hops]))
        rng.shuffle(ids)
        n_heldout = max(1, round(len(ids)*0.2)) if len(ids) > 1 else 0
        assignments.update({sid:'heldout_structure' if i < n_heldout else 'train'
                            for i,sid in enumerate(ids)})
    return assignments


def split_instances(instance_ids: list[str], structure_split: str, seed: int) -> dict[str,str]:
    if structure_split == 'heldout_structure':
        return dict.fromkeys(instance_ids,'heldout_structure')
    ids = sorted(instance_ids)
    random.Random(seed).shuffle(ids)
    n = min(2, max(0,len(ids)-2))
    return {iid:'heldout_instance' if i < n else 'train' for i,iid in enumerate(ids)}
