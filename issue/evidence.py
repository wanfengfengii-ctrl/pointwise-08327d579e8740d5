from dataclasses import dataclass
from fractions import Fraction
from itertools import groupby

from trial.samples import ShotRef


@dataclass(frozen=True)
class SeamPlateau:
    first: ShotRef
    last: ShotRef
    kn: Fraction


@dataclass(frozen=True)
class LocalTurn:
    ref: ShotRef
    kn: Fraction


@dataclass(frozen=True)
class SegmentEvidence:
    head: SeamPlateau
    tail: SeamPlateau | None
    turns: tuple[LocalTurn, ...]


def build_evidence(samples):
    """Keep two-sided local turns and the plates needed at either seam."""
    plateaus = []
    for load, run in groupby(samples, key=lambda sample: sample.kn):
        first = last = next(run)
        for last in run:
            pass
        plateaus.append(SeamPlateau(first.ref, last.ref, load))
    if not plateaus:
        raise ValueError('cannot issue evidence for an empty segment')
    if len(plateaus) == 1:
        return SegmentEvidence(plateaus[0], None, ())
    turns = tuple(
        LocalTurn(current.last, current.kn)
        for left, current, right in zip(plateaus, plateaus[1:], plateaus[2:])
        if (current.kn > left.kn) != (right.kn > current.kn)
    )
    return SegmentEvidence(plateaus[0], plateaus[-1], turns)
