from dataclasses import dataclass

from issue.codec import V1Piece, decode_piece
from receive.coverage import CoverageStatus, ExpectedManifest, check_coverage
from receive.identity import ReceiptIdentity, validate_piece_identity
from receive.store import AdmissionStore
from trial.plan import SegmentSpec


class IncompleteManifest(ValueError):
    pass


@dataclass(frozen=True)
class AcceptedPiece:
    spec: SegmentSpec
    identity: ReceiptIdentity
    piece: V1Piece


@dataclass(frozen=True)
class AcceptedManifest:
    expected: ExpectedManifest
    entries: tuple[AcceptedPiece, ...]
    status: CoverageStatus


def build_manifest(store: AdmissionStore, manifest_id):
    expected, stored_pieces = store.read_manifest_snapshot(manifest_id)
    by_segment = {}
    for stored in stored_pieces:
        piece = decode_piece(stored.wire)
        spec = validate_piece_identity(piece, expected)
        if stored.identity != ReceiptIdentity.for_piece(manifest_id, piece):
            raise RuntimeError('stored receipt does not bind its fixed piece')
        by_segment[spec.segment_id] = AcceptedPiece(spec, stored.identity, piece)
    entries = tuple(by_segment[spec.segment_id] for spec in expected.segments if spec.segment_id in by_segment)
    status = check_coverage(expected, (entry.spec for entry in entries))
    return AcceptedManifest(expected, entries, status)


def require_ready_manifest(store: AdmissionStore, manifest_id):
    manifest = build_manifest(store, manifest_id)
    if not manifest.status.ready:
        raise IncompleteManifest(f'missing segments: {manifest.status.missing!r}')
    return manifest
