from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from fractions import Fraction

from issue.codec import decode_piece, encode_piece
from issue.register import IssueRegister, issue_segment
from receive.admission import receive_segment
from receive.manifest import build_manifest
from receive.store import AdmissionStore
from tests import RepositoryTest
from trial.store import RevisionStore


class HandoffTests(RepositoryTest):
    def test_out_of_order_readiness(self):
        revision, wires = self.issue((0, 4, 0), (1, 3))
        manifest_id = self.register(revision)
        first_arrival = receive_segment(self.admissions, manifest_id, wires[1])
        self.assertFalse(first_arrival.status.ready)
        self.assertEqual(first_arrival.status.missing, ('shift-1',))
        self.assertTrue(receive_segment(self.admissions, manifest_id, wires[0]).status.ready)
        manifest = build_manifest(self.admissions, manifest_id)
        self.assertEqual([(entry.spec.first_shot, entry.spec.last_shot) for entry in manifest.entries], [(1, 1), (2, 3)])
        self.assertEqual(manifest.entries[1].identity, first_arrival.identity)

    def test_replay_preserves_slot_and_reports_current_readiness(self):
        revision, wires = self.issue((0, 4, 0), (1, 3))
        manifest_id = self.register(revision)
        first = receive_segment(self.admissions, manifest_id, wires[1])
        self.assertEqual(receive_segment(self.admissions, manifest_id, '\n' + wires[1]), first)
        self.assertEqual(len(self.admissions.read_manifest_snapshot(manifest_id)[1]), 1)
        receive_segment(self.admissions, manifest_id, wires[0])
        replay = receive_segment(self.admissions, manifest_id, wires[1])
        self.assertEqual(replay.identity, first.identity)
        self.assertTrue(replay.status.ready)
        self.assertEqual(len(self.admissions.read_manifest_snapshot(manifest_id)[1]), 2)

    def test_issue_binding_and_fixed_retrieval(self):
        first, first_wires = self.issue(cuts=(3, 7))
        second, _ = self.issue(cuts=(6, 7))
        revisions = self.open_store(RevisionStore, self.source_path)
        register = self.open_store(IssueRegister, self.source_path)
        prior_count = register.count()
        with self.assertRaises(KeyError):
            issue_segment(revisions, register, first.revision_id, second.plan.segments[0])
        with self.assertRaises(KeyError):
            issue_segment(revisions, register, 'absent', 'shift-1')
        self.assertEqual(register.count(), prior_count)
        self.assertEqual(issue_segment(revisions, register, first.revision_id, first.plan.segments[0]), first_wires[0])
        self.assertEqual(register.count(), prior_count)
        self.assertEqual(decode_piece(first_wires[0]).provenance.revision_id, first.revision_id)

    def test_seam_evidence_round_trip(self):
        revision, wires = self.issue(cuts=(6, 7))
        manifest_id = self.register(revision)
        for wire in reversed(wires):
            receive_segment(self.admissions, manifest_id, wire)
        left, right = (entry.piece for entry in build_manifest(self.admissions, manifest_id).entries)
        self.assertEqual(encode_piece(left), wires[0])
        self.assertEqual([(turn.ref.shot, turn.ref.source, turn.kn) for turn in left.evidence.turns],
                         [(4, 'bench/4', 4), (5, 'bench/5', 1)])
        self.assertEqual((left.evidence.tail.last.shot, left.evidence.tail.last.source), (6, 'bench/6'))
        self.assertEqual((right.evidence.head.first.shot, right.evidence.head.last.source), (7, 'bench/7'))
        self.assertIsNone(right.evidence.tail)
        self.assertNotIn('bench/2', wires[0])
        self.assertNotIn('bench/3', wires[0])

    def test_mixed_revision_cannot_occupy_slot(self):
        revision, wires = self.issue(cuts=(3, 7))
        _, newer = self.issue((0, 8, 8, 8, 1, 3, 0), (3, 7))
        manifest_id = self.register(revision)
        receive_segment(self.admissions, manifest_id, wires[1])
        previous = self.admissions.read_manifest_snapshot(manifest_id)
        with self.assertRaisesRegex(ValueError, 'different trial or revision'):
            receive_segment(self.admissions, manifest_id, newer[0])
        self.assertEqual(self.admissions.read_manifest_snapshot(manifest_id), previous)
        self.assertEqual(self.archive.counts(), (0, 0))
        self.assertTrue(receive_segment(self.admissions, manifest_id, wires[0]).status.ready)

    def test_different_fixed_piece_cannot_replace_slot(self):
        revision, wires = self.issue(cuts=(3, 7))
        manifest_id = self.register(revision)
        accepted = receive_segment(self.admissions, manifest_id, wires[0])
        piece = decode_piece(wires[0])
        changed = replace(piece, evidence=replace(piece.evidence, tail=replace(piece.evidence.tail, kn=Fraction(5))))
        wire = encode_piece(changed)
        self.assertNotEqual(decode_piece(wire).piece_id, piece.piece_id)
        with self.assertRaisesRegex(ValueError, 'different fixed piece'):
            receive_segment(self.admissions, manifest_id, wire)
        entries = build_manifest(self.admissions, manifest_id).entries
        self.assertEqual([(entry.identity, entry.piece) for entry in entries], [(accepted.identity, piece)])

    def test_out_of_bounds_evidence_cannot_occupy_slot(self):
        revision, wires = self.issue(cuts=(3, 7))
        manifest_id = self.register(revision)
        piece = decode_piece(wires[0])
        ref = replace(piece.evidence.head.first, shot=0)
        bad_head = replace(piece.evidence.head, first=ref, last=ref)
        bad_piece = replace(piece, evidence=replace(piece.evidence, head=bad_head))
        wire = encode_piece(bad_piece)
        self.assertEqual(decode_piece(wire).provenance, piece.provenance)
        with self.assertRaisesRegex(ValueError, 'outside the segment'):
            receive_segment(self.admissions, manifest_id, wire)
        self.assertEqual(build_manifest(self.admissions, manifest_id).entries, ())

    def test_two_connections_replay_one_identity(self):
        revision, wires = self.issue(cuts=(3, 7))
        manifest_id = self.register(revision)

        def receive():
            with closing(AdmissionStore(self.center_path)) as store:
                return receive_segment(store, manifest_id, wires[0])

        with ThreadPoolExecutor(max_workers=2) as executor:
            attempts = [executor.submit(receive) for _ in range(2)]
            first, second = (attempt.result() for attempt in attempts)
        self.assertEqual(first, second)
        self.assertEqual(first.status.missing, ('shift-2',))
        self.assertEqual(len(self.admissions.read_manifest_snapshot(manifest_id)[1]), 1)
