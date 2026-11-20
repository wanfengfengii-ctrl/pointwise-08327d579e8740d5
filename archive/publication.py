from archive.receipts import store_receipt
from archive.reports import PublishedReport, store_report
from archive.store import ArchiveStore
from receive.manifest import require_ready_manifest
from receive.store import AdmissionStore
from wear.assessment import assess


def publish(admissions: AdmissionStore, archive: ArchiveStore, manifest_id, band_edges, *, before_commit=None):
    manifest = require_ready_manifest(admissions, manifest_id)
    assessment = assess(manifest, band_edges)
    with archive.publication_transaction() as connection:
        report = store_report(connection, manifest, assessment)
        receipt = store_receipt(connection, report.report_id, report.manifest_id)
        if before_commit is not None:
            before_commit()
    return PublishedReport(report, receipt)
