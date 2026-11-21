from dataclasses import dataclass
from fractions import Fraction

from issue.work_evidence import split_anchors
from receive.manifest import IncompleteManifest
from trial.samples import ShotRef
from wear.bands import BandTotal, summarize_bands, validate_band_edges


@dataclass(frozen=True)
class WorkPoint:
    """An anchor with its whole-trial cumulative original-path work."""
    ref: ShotRef
    kn: Fraction
    travel: Fraction
    integral: Fraction


@dataclass(frozen=True)
class WorkTurn:
    ref: ShotRef
    kn: Fraction
    travel: Fraction


@dataclass(frozen=True)
class WorkCycle:
    first: ShotRef
    last: ShotRef
    amplitude: Fraction
    weight: Fraction
    work: Fraction

    def to_data(self):
        return {
            'first': self.first.to_data(),
            'last': self.last.to_data(),
            'amplitude': str(self.amplitude),
            'weight': str(self.weight),
            'work_j': str(self.work),
        }

    @classmethod
    def from_data(cls, data):
        return cls(ShotRef(**data['first']), ShotRef(**data['last']),
                   Fraction(data['amplitude']), Fraction(data['weight']), Fraction(data['work_j']))


@dataclass(frozen=True)
class WorkAssessment:
    turns: tuple[WorkTurn, ...]
    cycles: tuple[WorkCycle, ...]
    band_edges: tuple[Fraction, ...]
    bands: tuple[BandTotal, ...]
    total_work: Fraction
    remaining_work: Fraction


def _global_points(segments):
    """Attach whole-trial cumulative work to every anchor; each cross-shift edge
    between truly adjacent shots is metered exactly once from its anchor loads
    and signed travel difference."""
    seams = []
    for left, right in zip(segments, segments[1:]):
        tail, head = left[-1], right[0]
        seams.append((tail.kn + head.kn) * (head.travel - tail.travel) / 2)
    points = []
    base = Fraction(0)
    for index, anchors in enumerate(segments):
        if index:
            base += segments[index - 1][-1].integral + seams[index - 1]
        points.append(tuple(
            WorkPoint(anchor.ref, anchor.kn, anchor.travel, base + anchor.integral)
            for anchor in anchors
        ))
    total = base + segments[-1][-1].integral
    return points, total


def _restore_turns(segments):
    """Restore turns from complete shot-ordered work evidence, keeping the V1
    caliber for seam plateaus, actual boundary shots and same-direction anchors."""
    first = None
    candidates = []
    for points in segments:
        head_first, head_last, turns, _, tail_last = split_anchors(points)
        if first is None:
            first = head_first
        candidates_tail = (tail_last,) if tail_last is not None else ()
        for point in (head_last, *turns, *candidates_tail):
            if candidates and candidates[-1].kn == point.kn:
                candidates[-1] = point
            else:
                candidates.append(point)
    if first is None:
        raise ValueError('turn restoration requires at least one segment')
    restored = [first]
    for left, current, right in zip(candidates, candidates[1:], candidates[2:]):
        if (current.kn > left.kn) != (right.kn > current.kn):
            restored.append(current)
    last = candidates[-1]
    if last.ref != first.ref:
        restored.append(last)
    return restored


def _count_work_cycles(restored):
    """Eliminate four-point windows in V1 order. A complete cycle meters the
    current inner path minus its endpoint chord, which then replaces that path;
    each half cycle meters its remaining segment without applying the weight."""
    remaining = list(restored)
    works = [right.integral - left.integral for left, right in zip(remaining, remaining[1:])]
    cycles = []
    while len(remaining) >= 4:
        for index in range(len(remaining) - 3):
            left, first, last, right = remaining[index:index + 4]
            amplitude = abs(last.kn - first.kn)
            if 0 < amplitude <= min(abs(first.kn - left.kn), abs(right.kn - last.kn)):
                chord = (first.kn + last.kn) * (last.travel - first.travel) / 2
                work = works[index + 1] - chord
                cycles.append(WorkCycle(first.ref, last.ref, amplitude, Fraction(1), work))
                del remaining[index + 1:index + 3]
                works[index:index + 3] = [works[index] + chord + works[index + 2]]
                break
        else:
            break
    for index, (first, last) in enumerate(zip(remaining, remaining[1:])):
        amplitude = abs(last.kn - first.kn)
        if amplitude > 0:
            cycles.append(WorkCycle(first.ref, last.ref, amplitude, Fraction(1, 2), works[index]))
    remaining_work = sum(works, Fraction(0))
    return tuple(cycles), remaining_work


def assess_work(manifest, band_edges):
    if not manifest.status.ready:
        raise IncompleteManifest(f'missing segments: {manifest.status.missing!r}')
    edges = validate_band_edges(band_edges)
    segments = [entry.piece.evidence.anchors for entry in manifest.entries]
    points, total_work = _global_points(segments)
    restored = _restore_turns(points)
    cycles, remaining_work = _count_work_cycles(restored)
    turns = tuple(WorkTurn(point.ref, point.kn, point.travel) for point in restored)
    return WorkAssessment(turns, cycles, edges, summarize_bands(cycles, edges), total_work, remaining_work)
