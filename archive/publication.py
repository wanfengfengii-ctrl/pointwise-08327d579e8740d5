from archive.receipts import store_receipt, store_work_receipt
from archive.reports import PublishedReport, store_report, store_work_report
from archive.store import ArchiveStore
from receive.manifest import require_ready_manifest, require_ready_work_manifest
from receive.store import AdmissionStore
from wear.assessment import assess
from wear.work import assess_work


def publish(admissions: AdmissionStore, archive: ArchiveStore, manifest_id, band_edges, *, before_commit=None):
    manifest = require_ready_manifest(admissions, manifest_id)
    assessment = assess(manifest, band_edges)
    with archive.publication_transaction() as connection:
        report = store_report(connection, manifest, assessment)
        receipt = store_receipt(connection, report.report_id, report.manifest_id)
        if before_commit is not None:
            before_commit()
    return PublishedReport(report, receipt)


def publish_work(admissions: AdmissionStore, archive: ArchiveStore, manifest_id, band_edges, *, before_commit=None):
    manifest = require_ready_work_manifest(admissions, manifest_id)
    assessment = assess_work(manifest, band_edges)
    with archive.publication_transaction() as connection:
        report = store_work_report(connection, manifest, assessment)
        receipt = store_work_receipt(connection, report.report_id, report.manifest_id)
        if before_commit is not None:
            before_commit()
    return PublishedReport(report, receipt)
