import json
from fractions import Fraction

from archive.export import export_report
from archive.publication import publish
from archive.reports import read
from archive.store import ArchiveStore
from issue.codec import decode_piece
from issue.register import IssueRegister, issue_segment
from receive.admission import receive_segment
from receive.manifest import IncompleteManifest, require_ready_manifest
from receive.store import AdmissionStore
from tests import EDGES, RepositoryTest, ledger
from trial.revisions import load_revision
from trial.store import RevisionStore
from wear.cycles import count_cycles
from wear.turns import restore_turns


HALF = Fraction(1, 2)


class PublicationTests(RepositoryTest):
    def test_late_piece_only_cannot_publish(self):
        revision, wires = self.issue((0, 4, 0), (1, 3))
        manifest_id = self.register(revision)
        receive_segment(self.admissions, manifest_id, wires[1])
        with self.assertRaises(IncompleteManifest):
            publish(self.admissions, self.archive, manifest_id, EDGES)
        self.assertEqual(self.archive.counts(), (0, 0))
        receive_segment(self.admissions, manifest_id, wires[0])
        result = publish(self.admissions, self.archive, manifest_id, EDGES)
        self.assertEqual(ledger(result.report.cycles), [(1, 2, 4, HALF), (2, 3, 4, HALF)])
        self.assertEqual(self.archive.counts(), (1, 1))

    def test_partial_piece_with_cycles_cannot_publish(self):
        revision, wires = self.issue(cuts=(3, 7))
        manifest_id = self.register(revision)
        tail = decode_piece(wires[1])
        self.assertEqual(ledger(count_cycles(restore_turns([tail.evidence]))),
                         [(5, 6, 2, 1), (4, 7, 4, HALF)])
        receive_segment(self.admissions, manifest_id, wires[1])
        with self.assertRaises(IncompleteManifest):
            publish(self.admissions, self.archive, manifest_id, EDGES)
        self.assertEqual(self.archive.counts(), (0, 0))
        receive_segment(self.admissions, manifest_id, wires[0])
        result = publish(self.admissions, self.archive, manifest_id, EDGES)
        self.assertEqual(ledger(result.report.cycles), [(5, 6, 2, 1), (1, 4, 4, HALF), (4, 7, 4, HALF)])
        self.assertEqual([band.count for band in result.report.bands], [0, 1, 1])
        self.assertEqual(result.receipt.manifest_id, manifest_id)

    def test_illegal_bands_create_no_archive_rows(self):
        _, manifest_id, _ = self.ready()
        for edges in ((0, 2, 2), None, (), ('unknown',), (-1, 2), '2', (0, 3, 2)):
            with self.subTest(edges=edges), self.assertRaises(ValueError):
                publish(self.admissions, self.archive, manifest_id, edges)
            self.assertEqual(self.archive.counts(), (0, 0))

    def test_staged_report_and_receipt_rollback_then_retry(self):
        _, manifest_id, _ = self.ready()
        observer = self.open_store(ArchiveStore, self.center_path)
        observed_before_failure = []

        def fail_before_commit():
            observed_before_failure.append(observer.counts())
            raise RuntimeError('commit interrupted')

        with self.assertRaisesRegex(RuntimeError, 'commit interrupted'):
            publish(self.admissions, self.archive, manifest_id, EDGES, before_commit=fail_before_commit)
        self.assertEqual(observed_before_failure, [(0, 0)])
        self.assertEqual(observer.counts(), (0, 0))
        self.assertTrue(require_ready_manifest(self.admissions, manifest_id).status.ready)
        result = publish(self.admissions, self.archive, manifest_id, EDGES)
        self.assertEqual(observer.counts(), (1, 1))
        self.assertEqual(read(observer, result.report.report_id), result)
        self.assertEqual(result.receipt.report_id, result.report.report_id)

    def test_original_and_corrected_reports_survive_reopen(self):
        first, old_manifest, _ = self.ready()
        original = publish(self.admissions, self.archive, old_manifest, EDGES)
        second, new_manifest, _ = self.ready((0, 1, 0), (1, 3), '1/3')
        corrected = publish(self.admissions, self.archive, new_manifest, (0, '1/3'))
        self.assertNotEqual(first.revision_id, second.revision_id)
        self.assertNotEqual(original.report.report_id, corrected.report.report_id)
        self.assertEqual(original.report.revision_id, first.revision_id)
        self.assertEqual(corrected.report.revision_id, second.revision_id)
        self.assertEqual(ledger(corrected.report.cycles), [(1, 2, Fraction(1, 3), HALF), (2, 3, Fraction(1, 3), HALF)])
        self.assertNotEqual(original.report.parents, corrected.report.parents)
        self.archive.close()
        self.admissions.close()
        reopened = self.open_store(ArchiveStore, self.center_path)
        self.assertEqual(read(reopened, original.report.report_id), original)
        self.assertEqual(read(reopened, corrected.report.report_id), corrected)
        self.assertEqual(json.loads(export_report(reopened, original.report.report_id)), original.to_data())
        self.assertEqual(json.loads(export_report(reopened, corrected.report.report_id))['report']['band_edges'], ['0', '1/3'])
        self.assertEqual(reopened.counts(), (2, 2))

    def test_unknown_report_has_no_side_effects(self):
        for accessor in (read, export_report):
            with self.subTest(accessor=accessor.__name__), self.assertRaises(KeyError):
                accessor(self.archive, 921)
        self.assertEqual(self.archive.counts(), (0, 0))

    def test_reinitialize_preserves_original_and_user_correction(self):
        first, first_manifest, first_wires = self.ready()
        original = publish(self.admissions, self.archive, first_manifest, EDGES)
        second, second_manifest, second_wires = self.ready((0, 1, 0), (2, 3), '1/3')
        corrected = publish(self.admissions, self.archive, second_manifest, (0, '1/3'))
        receipt_ids = [entry.identity for entry in require_ready_manifest(self.admissions, second_manifest).entries]
        revisions = self.open_store(RevisionStore, self.source_path)
        register = self.open_store(IssueRegister, self.source_path)
        for store in (revisions, register, self.admissions, self.archive):
            store.initialize()
            store.initialize()
            store.close()

        revisions = self.open_store(RevisionStore, self.source_path)
        register = self.open_store(IssueRegister, self.source_path)
        admissions = self.open_store(AdmissionStore, self.center_path)
        archive = self.open_store(ArchiveStore, self.center_path)
        for revision, wires in ((first, first_wires), (second, second_wires)):
            self.assertEqual(load_revision(revisions, revision.revision_id), revision)
            self.assertEqual(tuple(issue_segment(revisions, register, revision.revision_id, spec)
                                   for spec in revision.plan.segments), wires)
        self.assertEqual(revisions.count(), 2)
        self.assertEqual(register.count(), len(first_wires) + len(second_wires))
        self.assertEqual([entry.identity for entry in require_ready_manifest(admissions, second_manifest).entries], receipt_ids)
        self.assertEqual(read(archive, original.report.report_id), original)
        self.assertEqual(read(archive, corrected.report.report_id), corrected)
        self.assertEqual(archive.counts(), (2, 2))
