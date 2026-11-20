import hashlib
import json
from dataclasses import dataclass

from trial.plan import SegmentSpec, validate_segment_plan


@dataclass(frozen=True)
class ExpectedManifest:
    trial_id: str
    revision_id: str
    first_shot: int
    last_shot: int
    segments: tuple[SegmentSpec, ...]

    def __post_init__(self):
        if any(not isinstance(value, str) or not value.strip() for value in (self.trial_id, self.revision_id)):
            raise ValueError('a manifest requires trial and revision identities')
        ordered = validate_segment_plan(self.segments, self.first_shot, self.last_shot)
        object.__setattr__(self, 'segments', ordered)

    @classmethod
    def from_revision(cls, revision):
        return cls(revision.plan.trial_id, revision.revision_id, revision.first_shot, revision.last_shot, revision.plan.segments)

    def to_json(self):
        return json.dumps({
            'trial_id': self.trial_id,
            'revision_id': self.revision_id,
            'first_shot': self.first_shot,
            'last_shot': self.last_shot,
            'segments': [entry.to_data() for entry in self.segments],
        }, sort_keys=True, separators=(',', ':'))

    @classmethod
    def from_json(cls, document):
        data = json.loads(document)
        data['segments'] = tuple(SegmentSpec(**entry) for entry in data['segments'])
        return cls(**data)

    @property
    def manifest_id(self):
        return hashlib.sha256(self.to_json().encode('utf-8')).hexdigest()


@dataclass(frozen=True)
class CoverageStatus:
    missing: tuple[str, ...]

    @property
    def ready(self):
        return not self.missing


def check_coverage(expected: ExpectedManifest, received):
    expected_slots = {entry.segment_id: entry for entry in expected.segments}
    occupied = set()
    for entry in received:
        if expected_slots.get(entry.segment_id) != entry or entry.segment_id in occupied:
            raise ValueError(f'invalid coverage at segment {entry.segment_id!r}')
        occupied.add(entry.segment_id)
    return CoverageStatus(tuple(entry.segment_id for entry in expected.segments if entry.segment_id not in occupied))
