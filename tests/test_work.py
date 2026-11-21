import json
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory

from archive.export import export_report, export_work_report
from archive.publication import publish, publish_work
from archive.reports import read, read_work
from archive.store import ArchiveStore
from demo_work import run_work_cases
from issue.register import IssueRegister, issue_segment, issue_work_segment
from issue.work_codec import decode_work_piece, encode_work_piece
from receive.admission import receive_segment, receive_work_segment
from receive.coverage import ExpectedManifest
from receive.manifest import IncompleteManifest, build_work_manifest, require_ready_manifest, require_ready_work_manifest
from receive.store import AdmissionStore
from tests import EDGES, RepositoryTest, input_for, ledger, work_ledger
from trial.calibration import Calibration
from trial.revisions import freeze_work, load_revision
from trial.store import RevisionStore
from wear.assessment import assess
from wear.work import assess_work


HALF = Fraction(1, 2)
LOADS = (0, 8, 8, 3, 4, 5, 1, 9)
TRAVELS = (0, 1, 2, 3, 4, 6, 7, 8)
WORK_LEDGER = [(4, 6, 2, 1, Fraction(1, 2)), (3, 7, 7, 1, Fraction(-2)), (1, 8, 9, HALF, Fraction(79, 2))]


class WorkFreezeTests(RepositoryTest):
    def setUp(self):
        super().setUp()
        self.revisions = self.open_store(RevisionStore, self.source_path)
        self.plan, self.samples = input_for((0, 2, 0), (3,))

    def test_freeze_work_round_trips_travel(self):
        travel = {1: '0', 2: 3, 3: Fraction(-7, 5)}
        revision = freeze_work(self.revisions, self.plan, Calibration(2), self.samples, travel)
        self.assertEqual(revision.travel, (0, 3, Fraction(-7, 5)))
        self.assertEqual([sample.kn for sample in revision.samples], [0, 4, 0])
        reopened = self.open_store(RevisionStore, self.source_path)
        self.assertEqual(load_revision(reopened, revision.revision_id), revision)
        manifest = ExpectedManifest.from_revision(revision)
        self.assertEqual((manifest.revision_id, manifest.first_shot, manifest.last_shot), (revision.revision_id, 1, 3))

    def test_travel_must_exactly_cover_shots(self):
        for bad in ({1: 0, 2: 1}, {1: 0, 2: 1, 3: 2, 4: 3}, {1: 0, 2: 1, 9: 2}):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, 'exactly'):
                freeze_work(self.revisions, self.plan, Calibration(2), self.samples, bad)
        self.assertEqual(self.revisions.count(), 0)

    def test_travel_rejects_illegal_keys_and_values(self):
        for bad in ({'1': 0, 2: 1, 3: 2}, {1: True, 2: 1, 3: 2}, {1: 0.5, 2: 1, 3: 2},
                    {1: None, 2: 1, 3: 2}, {1: '1/0', 2: 1, 3: 2}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                freeze_work(self.revisions, self.plan, Calibration(2), self.samples, bad)
        for not_mapping in (None, 3, 'travel', [(1, 0), (2, 1), (3, 2)]):
            with self.subTest(bad=not_mapping), self.assertRaises(ValueError):
                freeze_work(self.revisions, self.plan, Calibration(2), self.samples, not_mapping)
        self.assertEqual(self.revisions.count(), 0)

    def test_travel_may_descend_stall_or_be_negative(self):
        revision = freeze_work(self.revisions, self.plan, Calibration(2), self.samples, {1: 5, 2: 5, 3: '-3/2'})
        self.assertEqual(revision.travel, (5, 5, Fraction(-3, 2)))
        self.assertEqual(self.revisions.count(), 1)


class WorkIssueTests(RepositoryTest):
    def test_fixed_bytes_reissue_and_reopen(self):
        revision, wires = self.issue_work(LOADS, TRAVELS, (2, 4, 6, 8))
        revisions = self.open_store(RevisionStore, self.source_path)
        register = self.open_store(IssueRegister, self.source_path)
        count = register.count()
        for spec, wire in zip(revision.plan.segments, wires):
            self.assertEqual(issue_work_segment(revisions, register, revision.revision_id, spec), wire)
            self.assertEqual(issue_work_segment(revisions, register, revision.revision_id, spec.segment_id), wire)
        self.assertEqual(register.count(), count)
        piece = decode_work_piece(wires[0])
        self.assertEqual(piece.provenance.revision_id, revision.revision_id)
        self.assertEqual(json.loads(wires[0])['version'], 2)

    def test_only_anchor_travel_leaves_the_station(self):
        _, wires = self.issue_work(LOADS, TRAVELS, (8,))
        (wire,) = wires
        piece = decode_work_piece(wire)
        self.assertEqual([(a.ref.shot, a.ref.source) for a in piece.evidence.anchors],
                         [(1, 'bench/1'), (3, 'bench/3'), (4, 'bench/4'), (6, 'bench/6'),
                          (7, 'bench/7'), (8, 'bench/8')])
        self.assertEqual([a.travel for a in piece.evidence.anchors], [0, 2, 3, 6, 7, 8])
        self.assertEqual([a.integral for a in piece.evidence.anchors],
                         [0, 12, Fraction(35, 2), 30, 33, 38])
        self.assertNotIn('bench/2', wire)
        self.assertNotIn('bench/5', wire)

    def test_unknown_revision_or_segment(self):
        revision, _ = self.issue_work(LOADS, TRAVELS, (8,))
        other, _ = self.issue_work((0, 1, 0), (0, 1, 0), (3,), trial_id='cy-99')
        revisions = self.open_store(RevisionStore, self.source_path)
        register = self.open_store(IssueRegister, self.source_path)
        count = register.count()
        with self.assertRaises(KeyError):
            issue_work_segment(revisions, register, 'absent', 'shift-1')
        with self.assertRaises(KeyError):
            issue_work_segment(revisions, register, revision.revision_id, 'absent')
        with self.assertRaises(KeyError):
            issue_work_segment(revisions, register, revision.revision_id, other.plan.segments[0])
        self.assertEqual(register.count(), count)

    def test_versions_use_their_own_entries(self):
        work_revision, _ = self.issue_work((0, 2, 0), (0, 1, 0), (3,))
        v1_revision, _ = self.issue((0, 2, 0), (3,))
        revisions = self.open_store(RevisionStore, self.source_path)
        register = self.open_store(IssueRegister, self.source_path)
        count = register.count()
        with self.assertRaisesRegex(ValueError, 'work segment entry'):
            issue_segment(revisions, register, work_revision.revision_id, 'shift-1')
        with self.assertRaisesRegex(ValueError, 'V1 segment entry'):
            issue_work_segment(revisions, register, v1_revision.revision_id, 'shift-1')
        self.assertEqual(register.count(), count)


class WorkAdmissionTests(RepositoryTest):
    def test_out_of_order_readiness(self):
        revision, wires = self.issue_work(LOADS, TRAVELS, (2, 4, 6, 8))
        manifest_id = self.register(revision)
        arrivals = [receive_work_segment(self.admissions, manifest_id, wire) for wire in reversed(wires)]
        self.assertEqual([arrival.status.ready for arrival in arrivals], [False, False, False, True])
        self.assertEqual(arrivals[0].status.missing, ('shift-1', 'shift-2', 'shift-3'))
        manifest = build_work_manifest(self.admissions, manifest_id)
        self.assertEqual([entry.spec.segment_id for entry in manifest.entries],
                         ['shift-1', 'shift-2', 'shift-3', 'shift-4'])
        self.assertEqual(manifest.entries[-1].identity, arrivals[0].identity)

    def test_replay_preserves_slot_and_reports_current_readiness(self):
        revision, wires = self.issue_work((0, 4, 0), (0, 1, 0), (1, 3))
        manifest_id = self.register(revision)
        first = receive_work_segment(self.admissions, manifest_id, wires[1])
        self.assertEqual(receive_work_segment(self.admissions, manifest_id, '\n' + wires[1] + '\n'), first)
        self.assertEqual(len(self.admissions.read_manifest_snapshot(manifest_id)[1]), 1)
        receive_work_segment(self.admissions, manifest_id, wires[0])
        replay = receive_work_segment(self.admissions, manifest_id, wires[1])
        self.assertEqual(replay.identity, first.identity)
        self.assertTrue(replay.status.ready)
        self.assertEqual(len(self.admissions.read_manifest_snapshot(manifest_id)[1]), 2)

    def test_same_slot_rejects_different_fixed_piece(self):
        revision, wires = self.issue_work((0, 4, 0), (0, 1, 0), (1, 3))
        manifest_id = self.register(revision)
        accepted = receive_work_segment(self.admissions, manifest_id, wires[0])
        piece = decode_work_piece(wires[0])
        changed = replace(piece.evidence.anchors[-1], travel=Fraction(9))
        wire = encode_work_piece(replace(piece, evidence=replace(piece.evidence, anchors=(*piece.evidence.anchors[:-1], changed))))
        self.assertNotEqual(decode_work_piece(wire).piece_id, piece.piece_id)
        with self.assertRaisesRegex(ValueError, 'different fixed piece'):
            receive_work_segment(self.admissions, manifest_id, wire)
        entries = build_work_manifest(self.admissions, manifest_id).entries
        self.assertEqual([(entry.identity, entry.piece) for entry in entries], [(accepted.identity, piece)])

    def test_tampered_wire_fails_identity_check(self):
        revision, wires = self.issue_work((0, 4, 0), (0, 1, 0), (1, 3))
        manifest_id = self.register(revision)
        document = json.loads(wires[0])
        document['evidence']['anchors'][-1]['travel_mm'] = '9'
        with self.assertRaisesRegex(ValueError, 'identity'):
            receive_work_segment(self.admissions, manifest_id, json.dumps(document))
        self.assertEqual(build_work_manifest(self.admissions, manifest_id).entries, ())

    def test_mixed_versions_are_rejected(self):
        work_revision, work_wires = self.issue_work((0, 4, 0), (0, 1, 0), (1, 3))
        v1_revision, v1_wires = self.issue((0, 4, 0), (1, 3))
        work_manifest = self.register(work_revision)
        v1_manifest = self.register(v1_revision)
        with self.assertRaisesRegex(ValueError, 'unsupported piece version'):
            receive_work_segment(self.admissions, work_manifest, v1_wires[0])
        with self.assertRaisesRegex(ValueError, 'unsupported piece version'):
            receive_segment(self.admissions, v1_manifest, work_wires[0])
        self.assertEqual(build_work_manifest(self.admissions, work_manifest).entries, ())

    def test_unknown_manifest_and_malformed_anchors(self):
        revision, wires = self.issue_work((0, 4, 2, 4, 0), (0, 1, 2, 3, 4), (5,))
        manifest_id = self.register(revision)
        with self.assertRaises(KeyError):
            receive_work_segment(self.admissions, 'absent', wires[0])
        piece = decode_work_piece(wires[0])
        self.assertEqual([anchor.ref.shot for anchor in piece.evidence.anchors], [1, 2, 3, 4, 5])

        def recrafted(anchors):
            return encode_work_piece(replace(piece, evidence=replace(piece.evidence, anchors=anchors)))

        anchors = piece.evidence.anchors
        shifted = (replace(anchors[0], ref=replace(anchors[0].ref, shot=0)), *anchors[1:])
        with self.assertRaisesRegex(ValueError, 'first shot'):
            receive_work_segment(self.admissions, manifest_id, recrafted(shifted))
        flat_loads = (anchors[0], replace(anchors[1], kn=anchors[0].kn), *anchors[2:])
        with self.assertRaisesRegex(ValueError, 'alternate'):
            receive_work_segment(self.admissions, manifest_id, recrafted(flat_loads))
        duplicated = (anchors[0], anchors[0], *anchors[1:])
        with self.assertRaisesRegex(ValueError, 'increasing'):
            receive_work_segment(self.admissions, manifest_id, recrafted(duplicated))
        nonzero_base = (replace(anchors[0], integral=Fraction(1)), *anchors[1:])
        with self.assertRaisesRegex(ValueError, 'start at zero'):
            receive_work_segment(self.admissions, manifest_id, recrafted(nonzero_base))
        self.assertEqual(build_work_manifest(self.admissions, manifest_id).entries, ())

    def test_mixed_revision_cannot_occupy_slot(self):
        revision, wires = self.issue_work((0, 4, 0), (0, 1, 0), (1, 3))
        _, newer = self.issue_work((0, 4, 0), (0, 2, 0), (1, 3))
        manifest_id = self.register(revision)
        receive_work_segment(self.admissions, manifest_id, wires[1])
        previous = self.admissions.read_manifest_snapshot(manifest_id)
        with self.assertRaisesRegex(ValueError, 'different trial or revision'):
            receive_work_segment(self.admissions, manifest_id, newer[0])
        self.assertEqual(self.admissions.read_manifest_snapshot(manifest_id), previous)
        self.assertEqual(self.archive.work_counts(), (0, 0))
        self.assertTrue(receive_work_segment(self.admissions, manifest_id, wires[0]).status.ready)

    def test_two_connections_replay_one_identity(self):
        revision, wires = self.issue_work((0, 4, 0), (0, 1, 0), (1, 3))
        manifest_id = self.register(revision)

        def receive():
            with closing(AdmissionStore(self.center_path)) as store:
                return receive_work_segment(store, manifest_id, wires[0])

        with ThreadPoolExecutor(max_workers=2) as executor:
            attempts = [executor.submit(receive) for _ in range(2)]
            first, second = (attempt.result() for attempt in attempts)
        self.assertEqual(first, second)
        self.assertEqual(first.status.missing, ('shift-2',))
        self.assertEqual(len(self.admissions.read_manifest_snapshot(manifest_id)[1]), 1)


class WorkPublicationTests(RepositoryTest):
    def test_missing_pieces_cannot_sign(self):
        revision, wires = self.issue_work(LOADS, TRAVELS, (2, 4, 6, 8))
        manifest_id = self.register(revision)
        for wire in wires[1:]:
            receive_work_segment(self.admissions, manifest_id, wire)
        with self.assertRaises(IncompleteManifest):
            publish_work(self.admissions, self.archive, manifest_id, EDGES)
        self.assertEqual(self.archive.work_counts(), (0, 0))
        receive_work_segment(self.admissions, manifest_id, wires[0])
        signed = publish_work(self.admissions, self.archive, manifest_id, EDGES)
        self.assertEqual(self.archive.work_counts(), (1, 1))
        self.assertEqual(work_ledger(signed.report.cycles), WORK_LEDGER)

    def test_illegal_bands_create_no_archive_rows(self):
        _, manifest_id, _ = self.ready_work(LOADS, TRAVELS, (8,))
        for edges in ((0, 2, 2), None, (), ('unknown',), (-1, 2), '2', (0, 3, 2)):
            with self.subTest(edges=edges), self.assertRaises(ValueError):
                publish_work(self.admissions, self.archive, manifest_id, edges)
            self.assertEqual(self.archive.work_counts(), (0, 0))

    def test_whole_and_split_segmentations_agree(self):
        whole = publish_work(self.admissions, self.archive, self.ready_work(LOADS, TRAVELS, (8,))[1], EDGES)
        split = publish_work(self.admissions, self.archive, self.ready_work(LOADS, TRAVELS, (2, 4, 6, 8))[1], EDGES)
        for signed in (whole, split):
            self.assertEqual(work_ledger(signed.report.cycles), WORK_LEDGER)
            self.assertEqual((signed.report.total_work, signed.report.remaining_work), (38, Fraction(79, 2)))
            self.assertEqual([band.count for band in signed.report.bands], [0, 1, Fraction(3, 2)])
            complete = sum((cycle.work for cycle in signed.report.cycles if cycle.weight == 1), Fraction(0))
            self.assertEqual(complete + signed.report.remaining_work, signed.report.total_work)
        self.assertEqual([parent.segment_id for parent in split.report.parents],
                         ['shift-1', 'shift-2', 'shift-3', 'shift-4'])

    def test_staged_report_and_receipt_rollback_then_retry(self):
        _, manifest_id, _ = self.ready_work(LOADS, TRAVELS, (8,))
        observer = self.open_store(ArchiveStore, self.center_path)
        observed = []

        def fail_before_commit():
            observed.append(observer.work_counts())
            raise RuntimeError('commit interrupted')

        with self.assertRaisesRegex(RuntimeError, 'commit interrupted'):
            publish_work(self.admissions, self.archive, manifest_id, EDGES, before_commit=fail_before_commit)
        self.assertEqual(observed, [(0, 0)])
        self.assertEqual(observer.work_counts(), (0, 0))
        self.assertTrue(require_ready_work_manifest(self.admissions, manifest_id).status.ready)
        signed = publish_work(self.admissions, self.archive, manifest_id, EDGES)
        self.assertEqual(observer.work_counts(), (1, 1))
        self.assertEqual(read_work(observer, signed.report.report_id), signed)
        self.assertEqual(signed.receipt.report_id, signed.report.report_id)

    def test_signed_values_survive_reopen_and_export_exactly(self):
        revision, manifest_id, wires = self.ready_work(LOADS, TRAVELS, (2, 4, 6, 8))
        signed = publish_work(self.admissions, self.archive, manifest_id, EDGES)
        receipt_ids = [entry.identity for entry in require_ready_work_manifest(self.admissions, manifest_id).entries]
        self.archive.close()
        self.admissions.close()
        archive = self.open_store(ArchiveStore, self.center_path)
        admissions = self.open_store(AdmissionStore, self.center_path)
        retrieved = read_work(archive, signed.report.report_id)
        self.assertEqual(retrieved, signed)
        exported = export_work_report(archive, signed.report.report_id)
        self.assertEqual(json.loads(exported), signed.to_data())
        self.assertIn('"total_work_j":"38"', exported)
        self.assertIn('"remaining_work_j":"79/2"', exported)
        self.assertIn('"work_j":"-2"', exported)
        self.assertEqual([entry.identity for entry in require_ready_work_manifest(admissions, manifest_id).entries],
                         receipt_ids)
        self.assertEqual([parent.piece_id for parent in retrieved.report.parents],
                         [identity.piece_id for identity in receipt_ids])
        with self.assertRaises(KeyError):
            read_work(archive, 921)
        with self.assertRaises(KeyError):
            export_work_report(archive, 921)

    def test_reinitialize_preserves_issued_received_and_signed(self):
        revision, manifest_id, wires = self.ready_work(LOADS, TRAVELS, (2, 4, 6, 8))
        signed = publish_work(self.admissions, self.archive, manifest_id, EDGES)
        receipt_ids = [entry.identity for entry in require_ready_work_manifest(self.admissions, manifest_id).entries]
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
        self.assertEqual(load_revision(revisions, revision.revision_id), revision)
        self.assertEqual(tuple(issue_work_segment(revisions, register, revision.revision_id, spec)
                               for spec in revision.plan.segments), wires)
        self.assertEqual([entry.identity for entry in require_ready_work_manifest(admissions, manifest_id).entries],
                         receipt_ids)
        self.assertEqual(read_work(archive, signed.report.report_id), signed)
        self.assertEqual(archive.work_counts(), (1, 1))

    def test_correction_keeps_original_report_readable(self):
        first, first_manifest, _ = self.ready_work((0, 2, 0), (0, 1, 2), (3,))
        original = publish_work(self.admissions, self.archive, first_manifest, (0,))
        second, second_manifest, _ = self.ready_work((0, 2, 0), (0, -1, -2), (3,))
        corrected = publish_work(self.admissions, self.archive, second_manifest, (0,))
        self.assertNotEqual(first.revision_id, second.revision_id)
        self.assertNotEqual(original.report.report_id, corrected.report.report_id)
        self.assertEqual(original.report.total_work, 2)
        self.assertEqual(corrected.report.total_work, -2)
        self.assertEqual(original.report.revision_id, first.revision_id)
        self.assertEqual(corrected.report.revision_id, second.revision_id)
        self.archive.close()
        archive = self.open_store(ArchiveStore, self.center_path)
        self.assertEqual(read_work(archive, original.report.report_id), original)
        self.assertEqual(read_work(archive, corrected.report.report_id), corrected)
        self.assertEqual(archive.work_counts(), (2, 2))

    def test_v1_and_v2_archives_stay_separate(self):
        v1_revision, v1_wires = self.issue((0, 4, 0), (1, 3))
        v1_manifest = self.register(v1_revision)
        for wire in reversed(v1_wires):
            receive_segment(self.admissions, v1_manifest, wire)
        v1_signed = publish(self.admissions, self.archive, v1_manifest, EDGES)
        _, work_manifest, _ = self.ready_work((0, 4, 0), (0, 1, 0), (1, 3))
        work_signed = publish_work(self.admissions, self.archive, work_manifest, EDGES)
        self.assertEqual(self.archive.counts(), (1, 1))
        self.assertEqual(self.archive.work_counts(), (1, 1))
        self.assertEqual(read(self.archive, v1_signed.report.report_id), v1_signed)
        self.assertEqual(read_work(self.archive, work_signed.report.report_id), work_signed)
        self.assertNotIn('total_work_j', export_report(self.archive, v1_signed.report.report_id))
        self.assertEqual(json.loads(export_report(self.archive, v1_signed.report.report_id)), v1_signed.to_data())
        self.assertEqual(json.loads(export_work_report(self.archive, work_signed.report.report_id)),
                         work_signed.to_data())

    def test_report_numbers_are_version_scoped(self):
        _, work_manifest, _ = self.ready_work((0, 4, 0), (0, 1, 0), (1, 3))
        work_signed = publish_work(self.admissions, self.archive, work_manifest, EDGES)
        with self.assertRaises(KeyError):
            read(self.archive, work_signed.report.report_id)
        with self.assertRaises(KeyError):
            export_report(self.archive, work_signed.report.report_id)
        v1_revision, v1_wires = self.issue((0, 4, 0), (1, 3))
        v1_manifest = self.register(v1_revision)
        for wire in reversed(v1_wires):
            receive_segment(self.admissions, v1_manifest, wire)
        v1_signed = publish(self.admissions, self.archive, v1_manifest, EDGES)
        self.assertEqual(read_work(self.archive, work_signed.report.report_id), work_signed)
        self.assertEqual(read(self.archive, v1_signed.report.report_id), v1_signed)

    def test_mixed_version_manifest_cannot_sign(self):
        v1_revision, _ = self.issue((0, 4, 0), (1, 3))
        v1_manifest = self.register(v1_revision)
        _, work_manifest, work_wires = self.ready_work((0, 4, 0), (0, 1, 0), (1, 3))
        with self.assertRaises(ValueError):
            publish(self.admissions, self.archive, work_manifest, EDGES)
        with self.assertRaises(ValueError):
            publish_work(self.admissions, self.archive, v1_manifest, EDGES)
        self.assertEqual((self.archive.counts(), self.archive.work_counts()), ((0, 0), (0, 0)))


class WorkSampleTests(RepositoryTest):
    def test_v1_caliber_preserved_for_turns_cycles_and_bands(self):
        patterns = [
            ((0, 4, 4, 4, 1, 3, 0), (3, 6, 7)),
            ((0, 4, 4, 4, 2, 0), (2, 6)),
            ((0, 1, 2, 3), (2, 4)),
            ((2, 2, 4, 4, 2, 2), (1, 3, 5, 6)),
            ((0, 4, 2, 4, 2, 4, 0), (2, 5, 7)),
            ((4, 4, 4, 4), (2, 4)),
            ((4,), (1,)),
        ]
        for loads, cuts in patterns:
            with self.subTest(loads=loads, cuts=cuts):
                v1_revision, v1_wires = self.issue(loads, cuts)
                v1_manifest = self.register(v1_revision)
                for wire in reversed(v1_wires):
                    receive_segment(self.admissions, v1_manifest, wire)
                v1_assessment = assess(require_ready_manifest(self.admissions, v1_manifest), EDGES)
                travels = tuple(shot - 1 for shot in range(1, len(loads) + 1))
                _, work_manifest, _ = self.ready_work(loads, travels, cuts)
                work_assessment = assess_work(require_ready_work_manifest(self.admissions, work_manifest), EDGES)
                self.assertEqual([(turn.ref.shot, turn.kn) for turn in work_assessment.turns],
                                 [(turn.ref.shot, turn.kn) for turn in v1_assessment.turns])
                self.assertEqual(ledger(work_assessment.cycles), ledger(v1_assessment.cycles))
                self.assertEqual([band.count for band in work_assessment.bands],
                                 [band.count for band in v1_assessment.bands])

    def test_work_cases_json_offline_ledger(self):
        sample = Path(__file__).resolve().parents[1] / 'samples' / 'work_cases.json'
        with TemporaryDirectory() as directory:
            scenarios = run_work_cases(sample, Path(directory))
        self.assertEqual(len(scenarios), 7)
        for scenario in scenarios:
            self.assertEqual(scenario['actual'], scenario['expected'])
            self.assertEqual(scenario['downstream_actual'], scenario['downstream_expected'])
            self.assertTrue(all(scenario['downstream_checks'].values()))

    def test_inverted_travel_negates_work_but_keeps_wear_counts(self):
        forward = publish_work(self.admissions, self.archive, self.ready_work(LOADS, TRAVELS, (8,))[1], EDGES)
        inverted = publish_work(self.admissions, self.archive,
                                self.ready_work(LOADS, tuple(-value for value in TRAVELS), (8,))[1], EDGES)
        self.assertEqual(inverted.report.total_work, -forward.report.total_work)
        self.assertEqual(inverted.report.remaining_work, -forward.report.remaining_work)
        self.assertEqual([cycle.work for cycle in inverted.report.cycles],
                         [-cycle.work for cycle in forward.report.cycles])
        self.assertEqual([(c.first.shot, c.last.shot, c.amplitude, c.weight) for c in inverted.report.cycles],
                         [(c.first.shot, c.last.shot, c.amplitude, c.weight) for c in forward.report.cycles])
        self.assertEqual([band.count for band in inverted.report.bands],
                         [band.count for band in forward.report.bands])
