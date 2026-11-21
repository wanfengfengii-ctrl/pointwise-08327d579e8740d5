import hashlib
import json
from dataclasses import dataclass

from issue.provenance import PieceProvenance
from issue.work_evidence import WorkAnchor, WorkEvidence
from trial.calibration import parse_exact
from trial.samples import ShotRef


def _canonical(document):
    return json.dumps(document, sort_keys=True, separators=(',', ':'))


def _unique_object(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError(f'duplicate V2 field {key!r}')
        result[key] = value
    return result


def _fields(value, *keys):
    if not isinstance(value, dict) or value.keys() != set(keys):
        raise ValueError(f'expected V2 fields {keys!r}')
    return value


def _exact(value, label):
    if not isinstance(value, str):
        raise ValueError(f'V2 {label} must be rational text')
    parsed = parse_exact(value)
    if str(parsed) != value:
        raise ValueError(f'V2 {label} must use canonical rational text')
    return parsed


def _anchor_data(anchor):
    return {
        'shot': anchor.ref.shot,
        'source': anchor.ref.source,
        'kn': str(anchor.kn),
        'travel_mm': str(anchor.travel),
        'integral_j': str(anchor.integral),
    }


def _anchor(value):
    data = _fields(value, 'shot', 'source', 'kn', 'travel_mm', 'integral_j')
    ref = ShotRef(data['shot'], data['source'])
    return WorkAnchor(ref, _exact(data['kn'], 'load'), _exact(data['travel_mm'], 'travel'),
                      _exact(data['integral_j'], 'integral'))


@dataclass(frozen=True)
class V2Piece:
    provenance: PieceProvenance
    evidence: WorkEvidence

    def _unsigned_data(self):
        return {
            'version': 2,
            'provenance': self.provenance.to_data(),
            'evidence': {'anchors': [_anchor_data(anchor) for anchor in self.evidence.anchors]},
        }

    @property
    def piece_id(self):
        return _piece_id(self._unsigned_data())


def _piece_id(body):
    return hashlib.sha256(_canonical(body).encode('utf-8')).hexdigest()


def encode_work_piece(piece: V2Piece):
    body = piece._unsigned_data()
    body['piece_id'] = _piece_id(body)
    return _canonical(body)


def decode_work_piece(wire: str):
    if not isinstance(wire, str):
        raise ValueError('V2 piece must be JSON text')
    document = _fields(json.loads(wire, object_pairs_hook=_unique_object),
                       'version', 'piece_id', 'provenance', 'evidence')
    if type(document['version']) is not int or document['version'] != 2:
        raise ValueError('unsupported piece version')
    origin = _fields(document['provenance'], 'trial_id', 'revision_id', 'segment_id', 'first_shot', 'last_shot')
    evidence = _fields(document['evidence'], 'anchors')
    if not isinstance(evidence['anchors'], list) or not evidence['anchors']:
        raise ValueError('V2 evidence needs a nonempty anchor array')
    anchors = tuple(_anchor(entry) for entry in evidence['anchors'])
    shots = [anchor.ref.shot for anchor in anchors]
    if any(left >= right for left, right in zip(shots, shots[1:])):
        raise ValueError('V2 anchors must use strictly increasing shots')
    if anchors[0].integral != 0:
        raise ValueError('V2 integral must start at zero')
    piece = V2Piece(PieceProvenance(**origin), WorkEvidence(anchors))
    if document['piece_id'] != piece.piece_id:
        raise ValueError('fixed piece identity does not match its content')
    return piece
