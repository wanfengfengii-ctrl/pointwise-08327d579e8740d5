import json
from dataclasses import dataclass
from fractions import Fraction

from archive.receipts import PublicationReceipt, load_receipt
from archive.store import ArchiveStore
from wear.bands import BandTotal
from wear.cycles import Cycle


@dataclass(frozen=True)
class ParentPiece:
    segment_id: str
    first_shot: int
    last_shot: int
    piece_id: str
    receipt_id: str

    def to_data(self):
        return {
            'segment_id': self.segment_id, 'first_shot': self.first_shot, 'last_shot': self.last_shot,
            'piece_id': self.piece_id, 'receipt_id': self.receipt_id,
        }


@dataclass(frozen=True)
class ReportRecord:
    report_id: int
    manifest_id: str
    trial_id: str
    revision_id: str
    parents: tuple[ParentPiece, ...]
    band_edges: tuple[Fraction, ...]
    cycles: tuple[Cycle, ...]
    bands: tuple[BandTotal, ...]

    def to_data(self):
        return {
            'report_id': self.report_id, 'manifest_id': self.manifest_id,
            'trial_id': self.trial_id, 'revision_id': self.revision_id,
            **_detail(self.parents, self.band_edges, self.cycles, self.bands),
        }


@dataclass(frozen=True)
class PublishedReport:
    report: ReportRecord
    receipt: PublicationReceipt

    def to_data(self):
        return {'report': self.report.to_data(), 'receipt': self.receipt.to_data()}


def _detail(parents, edges, cycles, bands):
    return {
        'parents': [parent.to_data() for parent in parents],
        'band_edges': [str(edge) for edge in edges],
        'cycles': [cycle.to_data() for cycle in cycles],
        'bands': [band.to_data() for band in bands],
    }


def store_report(connection, manifest, assessment):
    expected = manifest.expected
    parents = tuple(
        ParentPiece(entry.spec.segment_id, entry.spec.first_shot, entry.spec.last_shot,
                    entry.identity.piece_id, entry.identity.receipt_id)
        for entry in manifest.entries
    )
    detail = _detail(parents, assessment.band_edges, assessment.cycles, assessment.bands)
    cursor = connection.execute('''
        INSERT INTO published_reports (manifest_id, trial_id, revision_id, detail) VALUES (?, ?, ?, ?)
    ''', (expected.manifest_id, expected.trial_id, expected.revision_id, json.dumps(detail, separators=(',', ':'))))
    return ReportRecord(cursor.lastrowid, expected.manifest_id, expected.trial_id, expected.revision_id,
                        parents, assessment.band_edges, assessment.cycles, assessment.bands)


def read(store: ArchiveStore, report_id):
    snapshot = store.read_snapshot(report_id)
    if snapshot is None:
        raise KeyError(report_id)
    detail = json.loads(snapshot['detail'])
    record = ReportRecord(
        snapshot['report_id'], snapshot['manifest_id'], snapshot['trial_id'], snapshot['revision_id'],
        tuple(ParentPiece(**entry) for entry in detail['parents']),
        tuple(Fraction(edge) for edge in detail['band_edges']),
        tuple(Cycle.from_data(entry) for entry in detail['cycles']),
        tuple(BandTotal.from_data(entry) for entry in detail['bands']),
    )
    return PublishedReport(record, load_receipt(snapshot))
