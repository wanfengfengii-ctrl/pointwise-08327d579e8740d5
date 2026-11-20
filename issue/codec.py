import hashlib
import json
from dataclasses import dataclass

from issue.evidence import LocalTurn, SeamPlateau, SegmentEvidence
from issue.provenance import PieceProvenance
from trial.calibration import parse_exact
from trial.samples import ShotRef


def _canonical(document):
    return json.dumps(document, sort_keys=True, separators=(',', ':'))


def _unique_object(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError(f'duplicate V1 field {key!r}')
        result[key] = value
    return result


def _fields(value, *keys):
    if not isinstance(value, dict) or value.keys() != set(keys):
        raise ValueError(f'expected V1 fields {keys!r}')
    return value


def _plateau_data(plateau):
    return {'first': plateau.first.to_data(), 'last': plateau.last.to_data(), 'kn': str(plateau.kn)}


def _ref(value):
    return ShotRef(**_fields(value, 'shot', 'source'))


def _load(value):
    if not isinstance(value, str):
        raise ValueError('V1 load must be rational text')
    load = parse_exact(value)
    if str(load) != value:
        raise ValueError('V1 load must use canonical rational text')
    return load


def _plateau(value):
    data = _fields(value, 'first', 'last', 'kn')
    return SeamPlateau(_ref(data['first']), _ref(data['last']), _load(data['kn']))


@dataclass(frozen=True)
class V1Piece:
    provenance: PieceProvenance
    evidence: SegmentEvidence

    def _unsigned_data(self):
        evidence = self.evidence
        return {
            'version': 1,
            'provenance': self.provenance.to_data(),
            'evidence': {
                'head': _plateau_data(evidence.head),
                'tail': None if evidence.tail is None else _plateau_data(evidence.tail),
                'turns': [{'ref': turn.ref.to_data(), 'kn': str(turn.kn)} for turn in evidence.turns],
            },
        }

    @property
    def piece_id(self):
        return _piece_id(self._unsigned_data())


def _piece_id(body):
    return hashlib.sha256(_canonical(body).encode('utf-8')).hexdigest()


def encode_piece(piece: V1Piece):
    body = piece._unsigned_data()
    body['piece_id'] = _piece_id(body)
    return _canonical(body)


def decode_piece(wire: str):
    if not isinstance(wire, str):
        raise ValueError('V1 piece must be JSON text')
    document = _fields(json.loads(wire, object_pairs_hook=_unique_object), 'version', 'piece_id', 'provenance', 'evidence')
    if type(document['version']) is not int or document['version'] != 1:
        raise ValueError('unsupported piece version')
    origin = _fields(document['provenance'], 'trial_id', 'revision_id', 'segment_id', 'first_shot', 'last_shot')
    evidence = _fields(document['evidence'], 'head', 'tail', 'turns')
    if not isinstance(evidence['turns'], list):
        raise ValueError('V1 turns must be an array')
    turns = []
    for entry in evidence['turns']:
        turn = _fields(entry, 'ref', 'kn')
        turns.append(LocalTurn(_ref(turn['ref']), _load(turn['kn'])))
    tail = None if evidence['tail'] is None else _plateau(evidence['tail'])
    piece = V1Piece(PieceProvenance(**origin), SegmentEvidence(_plateau(evidence['head']), tail, tuple(turns)))
    if document['piece_id'] != piece.piece_id:
        raise ValueError('fixed piece identity does not match its content')
    return piece
