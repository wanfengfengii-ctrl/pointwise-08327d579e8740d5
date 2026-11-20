from dataclasses import dataclass


@dataclass(frozen=True)
class SegmentSpec:
    segment_id: str
    first_shot: int
    last_shot: int

    def __post_init__(self):
        if not isinstance(self.segment_id, str) or not self.segment_id.strip():
            raise ValueError('segment identity is required')
        if type(self.first_shot) is not int or type(self.last_shot) is not int:
            raise ValueError('segment bounds must be integer shot numbers')
        if self.first_shot > self.last_shot:
            raise ValueError('segment bounds are reversed')

    def to_data(self):
        return {
            'segment_id': self.segment_id,
            'first_shot': self.first_shot,
            'last_shot': self.last_shot,
        }


@dataclass(frozen=True)
class TrialPlan:
    trial_id: str
    segments: tuple[SegmentSpec, ...]

    def __post_init__(self):
        if not isinstance(self.trial_id, str) or not self.trial_id.strip():
            raise ValueError('trial identity is required')
        object.__setattr__(self, 'segments', tuple(self.segments))


def validate_segment_plan(segments, first_shot, last_shot):
    """Return the unique, contiguous closed intervals in shot order."""
    if type(first_shot) is not int or type(last_shot) is not int or first_shot > last_shot:
        raise ValueError('invalid trial shot bounds')
    entries = tuple(segments)
    if not entries or any(not isinstance(entry, SegmentSpec) for entry in entries):
        raise ValueError('a trial needs at least one valid segment')
    ordered = tuple(sorted(entries, key=lambda entry: entry.first_shot))
    named = set()
    next_shot = first_shot
    for entry in ordered:
        if entry.segment_id in named:
            raise ValueError(f'duplicate segment identity {entry.segment_id!r}')
        if entry.first_shot != next_shot:
            raise ValueError(f'expected segment to start at shot {next_shot}')
        named.add(entry.segment_id)
        next_shot = entry.last_shot + 1
    if next_shot != last_shot + 1:
        raise ValueError('segment plan must end at the last shot')
    return ordered
