from dataclasses import dataclass


@dataclass(frozen=True)
class PieceProvenance:
    trial_id: str
    revision_id: str
    segment_id: str
    first_shot: int
    last_shot: int

    def __post_init__(self):
        for identity in (self.trial_id, self.revision_id, self.segment_id):
            if not isinstance(identity, str) or not identity.strip():
                raise ValueError('trial, revision and segment identities are required')
        if type(self.first_shot) is not int or type(self.last_shot) is not int:
            raise ValueError('piece bounds must be integer shot numbers')
        if self.first_shot > self.last_shot:
            raise ValueError('piece bounds are reversed')

    def to_data(self):
        return {
            'trial_id': self.trial_id,
            'revision_id': self.revision_id,
            'segment_id': self.segment_id,
            'first_shot': self.first_shot,
            'last_shot': self.last_shot,
        }


def bind_provenance(segment):
    return PieceProvenance(
        segment.revision.plan.trial_id, segment.revision.revision_id,
        segment.spec.segment_id, segment.spec.first_shot, segment.spec.last_shot,
    )
