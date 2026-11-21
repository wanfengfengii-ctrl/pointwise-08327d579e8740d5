from dataclasses import dataclass

from issue.codec import decode_piece, encode_piece
from issue.work_codec import decode_work_piece, encode_work_piece
from receive.coverage import CoverageStatus
from receive.identity import ReceiptIdentity, same_fixed_piece, validate_piece_identity
from receive.manifest import build_manifest, build_work_manifest
from receive.store import AdmissionStore
from receive.work_identity import same_fixed_work_piece, validate_work_piece_identity


@dataclass(frozen=True)
class AdmissionResult:
    identity: ReceiptIdentity
    status: CoverageStatus


def _receive(store: AdmissionStore, manifest_id, piece, encode, build, validate, same_fixed):
    with store.receipt_transaction() as connection:
        manifest = build(store, manifest_id)
        spec = validate(piece, manifest.expected)
        prior = next((entry for entry in manifest.entries if entry.spec == spec), None)
        if prior is not None:
            if not same_fixed(prior.piece, piece):
                raise ValueError(f'segment {spec.segment_id!r} already has a different fixed piece')
            result = AdmissionResult(prior.identity, manifest.status)
        else:
            identity = ReceiptIdentity.for_piece(manifest_id, piece)
            store.record_piece(connection, identity, encode(piece))
            status = build(store, manifest_id).status
            result = AdmissionResult(identity, status)
    return result


def receive_segment(store: AdmissionStore, manifest_id, wire):
    piece = decode_piece(wire)
    return _receive(store, manifest_id, piece, encode_piece, build_manifest,
                    validate_piece_identity, same_fixed_piece)


def receive_work_segment(store: AdmissionStore, manifest_id, wire):
    piece = decode_work_piece(wire)
    return _receive(store, manifest_id, piece, encode_work_piece, build_work_manifest,
                    validate_work_piece_identity, same_fixed_work_piece)
