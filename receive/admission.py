from dataclasses import dataclass

from issue.codec import decode_piece, encode_piece
from receive.coverage import CoverageStatus
from receive.identity import ReceiptIdentity, same_fixed_piece, validate_piece_identity
from receive.manifest import build_manifest
from receive.store import AdmissionStore


@dataclass(frozen=True)
class AdmissionResult:
    identity: ReceiptIdentity
    status: CoverageStatus


def receive_segment(store: AdmissionStore, manifest_id, wire):
    piece = decode_piece(wire)
    with store.receipt_transaction() as connection:
        manifest = build_manifest(store, manifest_id)
        spec = validate_piece_identity(piece, manifest.expected)
        prior = next((entry for entry in manifest.entries if entry.spec == spec), None)
        if prior is not None:
            if not same_fixed_piece(prior.piece, piece):
                raise ValueError(f'segment {spec.segment_id!r} already has a different fixed piece')
            result = AdmissionResult(prior.identity, manifest.status)
        else:
            identity = ReceiptIdentity.for_piece(manifest_id, piece)
            store.record_piece(connection, identity, encode_piece(piece))
            status = build_manifest(store, manifest_id).status
            result = AdmissionResult(identity, status)
    return result
