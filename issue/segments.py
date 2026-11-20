from dataclasses import dataclass

from trial.plan import SegmentSpec
from trial.revisions import Revision
from trial.samples import CalibratedSample


@dataclass(frozen=True)
class SegmentSlice:
    revision: Revision
    spec: SegmentSpec
    samples: tuple[CalibratedSample, ...]


def select_segment(revision: Revision, requested: str | SegmentSpec):
    segment_id = requested.segment_id if isinstance(requested, SegmentSpec) else requested
    spec = next((entry for entry in revision.plan.segments if entry.segment_id == segment_id), None)
    if spec is None or (isinstance(requested, SegmentSpec) and requested != spec):
        raise KeyError(f'segment {segment_id!r} does not match revision {revision.revision_id}')
    offset = revision.first_shot
    samples = revision.samples[spec.first_shot - offset:spec.last_shot - offset + 1]
    return SegmentSlice(revision, spec, samples)
