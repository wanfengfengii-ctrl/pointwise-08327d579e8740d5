import hashlib
from dataclasses import dataclass

from issue.codec import V1Piece
from receive.coverage import ExpectedManifest


@dataclass(frozen=True)
class ReceiptIdentity:
    manifest_id: str
    segment_id: str
    piece_id: str
    receipt_id: str

    @classmethod
    def for_piece(cls, manifest_id, piece):
        piece_id = piece.piece_id
        receipt_id = hashlib.sha256(f'{manifest_id}:{piece_id}'.encode('utf-8')).hexdigest()
        return cls(manifest_id, piece.provenance.segment_id, piece_id, receipt_id)


def _check_plateau(plateau, spec):
    if not spec.first_shot <= plateau.first.shot <= plateau.last.shot <= spec.last_shot:
        raise ValueError('seam plateau lies outside the segment')
    if plateau.first.shot == plateau.last.shot and plateau.first != plateau.last:
        raise ValueError('one shot has conflicting source references')


def validate_piece_identity(piece: V1Piece, expected: ExpectedManifest):
    origin = piece.provenance
    if (origin.trial_id, origin.revision_id) != (expected.trial_id, expected.revision_id):
        raise ValueError('piece belongs to a different trial or revision')
    spec = next((entry for entry in expected.segments if entry.segment_id == origin.segment_id), None)
    if spec is None or (spec.first_shot, spec.last_shot) != (origin.first_shot, origin.last_shot):
        raise ValueError('piece does not match the declared segment')
    head, tail, turns = piece.evidence.head, piece.evidence.tail, piece.evidence.turns
    _check_plateau(head, spec)
    if head.first.shot != spec.first_shot:
        raise ValueError('head plateau does not start at the first shot')
    if tail is None:
        if turns or head.last.shot != spec.last_shot:
            raise ValueError('a flat segment needs one plateau covering its full range')
        return spec
    _check_plateau(tail, spec)
    if tail.last.shot != spec.last_shot:
        raise ValueError('tail plateau does not end at the last shot')
    shots = [head.last.shot, *(turn.ref.shot for turn in turns), tail.first.shot]
    if any(left >= right for left, right in zip(shots, shots[1:])):
        raise ValueError('local turns must be strictly ordered inside the seam bounds')
    loads = [head.kn, *(turn.kn for turn in turns), tail.kn]
    deltas = [right - left for left, right in zip(loads, loads[1:])]
    if any(delta == 0 for delta in deltas) or any(left * right > 0 for left, right in zip(deltas, deltas[1:])):
        raise ValueError('local turns do not alternate between distinct loads')
    return spec


def same_fixed_piece(left: V1Piece, right: V1Piece):
    return left == right and left.piece_id == right.piece_id
