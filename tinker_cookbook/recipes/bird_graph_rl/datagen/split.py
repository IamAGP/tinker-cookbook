"""Seeded structure holdouts with deliberately unseen components."""
from __future__ import annotations
from collections import Counter, defaultdict
from dataclasses import dataclass
import json
import random
from .structures import Structure, canonical_path, components

@dataclass(frozen=True)
class SplitPlan:
    assignments: dict[str,str]
    novelty: dict[str,str]
    held_components: dict[str,str]
    unseen_components: dict[str,list[str]]


def plan_split(structures: list[Structure], seed: int) -> SplitPlan:
    ordered = sorted(structures,key=lambda s:s.structure_id)
    rng = random.Random(seed)
    rng.shuffle(ordered)
    extras = Counter(e for s in ordered for e in s.extras)
    if not extras or not any(s.path.hops == 4 for s in ordered):
        raise ValueError('A3 requires surviving extras and a four-hop path')
    # Minimum-size classes avoid overwhelming the intended 20% holdout.
    extra = min(sorted(extras),key=lambda e:extras[e])
    forced = {s.structure_id for s in ordered if extra in s.extras}
    four_paths = Counter(canonical_path(s.path) for s in ordered if s.path.hops == 4)
    path = min(sorted(four_paths),key=lambda p:four_paths[p])
    forced.update(s.structure_id for s in ordered if canonical_path(s.path) == path)
    pair_counts = Counter(json.dumps([json.loads(s.signature)['aggregation'],s.extras])
                          for s in ordered if s.extras and s.structure_id not in forced)
    if not pair_counts:
        raise ValueError('No independent surviving (aggregation, extras) pairing for A3')
    pair = min(sorted(pair_counts),key=lambda p:pair_counts[p])
    forced.update(s.structure_id for s in ordered if
                  json.dumps([json.loads(s.signature)['aggregation'],s.extras]) == pair)
    strata: dict[int,list[Structure]] = defaultdict(list)
    for s in ordered:
        strata[s.path.hops].append(s)
    held = set(forced)
    for hops,group in sorted(strata.items()):
        need = max(0,round(len(group)*.2)-sum(s.structure_id in held for s in group))
        candidates = [s for s in group if s.structure_id not in held]
        held.update(s.structure_id for s in candidates[:need])
    assignments = {s.structure_id:'heldout_structure' if s.structure_id in held else 'train'
                   for s in ordered}
    training_components = frozenset(c for s in ordered if s.structure_id not in held for c in components(s))
    missing = {s.structure_id:sorted(components(s)-training_components) for s in ordered if s.structure_id in held}
    novelty = {sid:'novel_component' if values else 'novel_combination' for sid,values in missing.items()}
    return SplitPlan(assignments,novelty,{'extra':extra,'four_hop_path':path,
                                        'aggregation_extras_pairing':pair},missing)


def split_structures(structures: list[Structure], seed: int) -> dict[str,str]:
    return plan_split(structures,seed).assignments


def split_instances(instance_ids: list[str], structure_split: str, seed: int) -> dict[str,str]:
    if structure_split == 'heldout_structure':
        return dict.fromkeys(instance_ids,'heldout_structure')
    ids = sorted(instance_ids)
    random.Random(seed).shuffle(ids)
    n = min(2,max(0,len(ids)-2))
    return {iid:'heldout_instance' if i < n else 'train' for i,iid in enumerate(ids)}
