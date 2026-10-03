"""Explicit, parameter-independent visitor-intent decisions made before splitting."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class Decision:
    keep: bool
    reason: str


def decide(mode: str) -> Decision:
    if mode in ('count','group','having'):
        return Decision(False,'counts matched combinations rather than distinct site entities')
    if mode == 'difference':
        return Decision(False,'score minus absolute score has no plausible visitor intent')
    return Decision(True,'distinct entities or an ordinary statistic about them')
