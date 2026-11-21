from issue.work_codec import V2Piece
from issue.work_evidence import split_anchors
from receive.coverage import ExpectedManifest


def _validate_structure(anchors):
    if len(anchors) == 1:
        return
    if all(anchor.kn == anchors[0].kn for anchor in anchors):
        if len(anchors) > 2:
            raise ValueError('a flat segment needs one plateau covering its full range')
        return
    _, _, turns, _, _ = split_anchors(anchors)
    loads = [anchors[0].kn, *(turn.kn for turn in turns), anchors[-1].kn]
    deltas = [right - left for left, right in zip(loads, loads[1:])]
    if any(delta == 0 for delta in deltas) or any(left * right > 0 for left, right in zip(deltas, deltas[1:])):
        raise ValueError('local turns do not alternate between distinct loads')


def validate_work_piece_identity(piece: V2Piece, expected: ExpectedManifest):
    origin = piece.provenance
    if (origin.trial_id, origin.revision_id) != (expected.trial_id, expected.revision_id):
        raise ValueError('piece belongs to a different trial or revision')
    spec = next((entry for entry in expected.segments if entry.segment_id == origin.segment_id), None)
    if spec is None or (spec.first_shot, spec.last_shot) != (origin.first_shot, origin.last_shot):
        raise ValueError('piece does not match the declared segment')
    anchors = piece.evidence.anchors
    if anchors[0].ref.shot != spec.first_shot:
        raise ValueError('head plateau does not start at the first shot')
    if anchors[-1].ref.shot != spec.last_shot:
        raise ValueError('tail plateau does not end at the last shot')
    _validate_structure(anchors)
    return spec


def same_fixed_work_piece(left: V2Piece, right: V2Piece):
    return left == right and left.piece_id == right.piece_id
