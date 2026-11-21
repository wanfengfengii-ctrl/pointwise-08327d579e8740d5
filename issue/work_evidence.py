from dataclasses import dataclass
from fractions import Fraction
from itertools import groupby

from trial.samples import ShotRef


@dataclass(frozen=True)
class WorkAnchor:
    """One exported anchor: load, source, calibrated travel and the cumulative
    original-path work from the segment's first shot up to this shot."""
    ref: ShotRef
    kn: Fraction
    travel: Fraction
    integral: Fraction


@dataclass(frozen=True)
class WorkEvidence:
    anchors: tuple[WorkAnchor, ...]


def split_anchors(anchors):
    """Split an anchor sequence into (head_first, head_last, turns, tail_first, tail_last).

    Works on any sequence of objects carrying a ``kn`` load. A flat segment yields
    no turns and no tail. Head and tail plateaus contribute their boundary shots;
    each interior turn contributes its own shot.
    """
    count = len(anchors)
    if count == 1 or all(anchor.kn == anchors[0].kn for anchor in anchors):
        return anchors[0], anchors[-1], (), None, None
    head_count = 2 if anchors[0].kn == anchors[1].kn else 1
    tail_count = 2 if anchors[-2].kn == anchors[-1].kn else 1
    turns = tuple(anchors[head_count:count - tail_count])
    return anchors[0], anchors[head_count - 1], turns, anchors[count - tail_count], anchors[-1]


def build_work_evidence(samples, travels):
    """Keep the V1-exportable anchors with their travel and original-path integrals.

    Anchors are the local turns plus the boundary shots of the head and tail
    plateaus; one shot appears once. Original measurement rows and the travel of
    every other shot stay at the station.
    """
    samples = tuple(samples)
    travels = tuple(travels)
    if not samples or len(samples) != len(travels):
        raise ValueError('work evidence needs samples aligned with calibrated travel')
    integrals = [Fraction(0)]
    for index in range(len(samples) - 1):
        edge = (samples[index].kn + samples[index + 1].kn) * (travels[index + 1] - travels[index]) / 2
        integrals.append(integrals[-1] + edge)
    plateaus = []
    for load, run in groupby(range(len(samples)), key=lambda index: samples[index].kn):
        indices = list(run)
        plateaus.append((indices[0], indices[-1], load))
    if len(plateaus) == 1:
        anchor_indices = [plateaus[0][0], plateaus[0][1]]
    else:
        anchor_indices = [plateaus[0][0], plateaus[0][1]]
        for left, current, right in zip(plateaus, plateaus[1:], plateaus[2:]):
            if (current[2] > left[2]) != (right[2] > current[2]):
                anchor_indices.append(current[1])
        anchor_indices += [plateaus[-1][0], plateaus[-1][1]]
    anchors = []
    seen = set()
    for index in anchor_indices:
        if index in seen:
            continue
        seen.add(index)
        sample = samples[index]
        anchors.append(WorkAnchor(sample.ref, sample.kn, travels[index], integrals[index]))
    return WorkEvidence(tuple(anchors))
