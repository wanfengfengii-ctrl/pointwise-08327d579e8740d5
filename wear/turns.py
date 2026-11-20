from dataclasses import dataclass
from fractions import Fraction

from trial.samples import ShotRef


@dataclass(frozen=True)
class Turn:
    ref: ShotRef
    kn: Fraction


def _segment_candidates(evidence):
    yield Turn(evidence.head.last, evidence.head.kn)
    for turn in evidence.turns:
        yield Turn(turn.ref, turn.kn)
    if evidence.tail is not None:
        yield Turn(evidence.tail.last, evidence.tail.kn)


def restore_turns(evidences):
    """Restore turns from the evidence of a complete, shot-ordered manifest."""
    first = None
    candidates = []
    for evidence in evidences:
        if first is None:
            first = Turn(evidence.head.first, evidence.head.kn)
        for point in _segment_candidates(evidence):
            if candidates and candidates[-1].kn == point.kn:
                candidates[-1] = point
            else:
                candidates.append(point)
    if first is None:
        raise ValueError('turn restoration requires at least one segment')

    # A seam anchor survives only if both sides show a reversal.
    turns = [first]
    for left, current, right in zip(candidates, candidates[1:], candidates[2:]):
        if (current.kn > left.kn) != (right.kn > current.kn):
            turns.append(current)
    last = candidates[-1]
    if last.ref != first.ref:
        turns.append(last)
    return tuple(turns)
