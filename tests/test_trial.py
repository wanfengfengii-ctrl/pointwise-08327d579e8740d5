from fractions import Fraction

from tests import RepositoryTest, input_for
from trial.calibration import Calibration
from trial.plan import SegmentSpec, TrialPlan
from trial.revisions import freeze, load_revision
from trial.samples import RawSample
from trial.store import RevisionStore


class TrialTests(RepositoryTest):
    def setUp(self):
        super().setUp()
        self.revisions = self.open_store(RevisionStore, self.source_path)
        self.plan, self.samples = input_for((0, 2, 0), (3,))

    def test_exact_calibration_preserves_source(self):
        revision = freeze(self.revisions, self.plan, Calibration(2), self.samples)
        self.assertEqual([sample.kn for sample in revision.samples], [0, 4, 0])
        self.assertEqual([sample.reading for sample in revision.samples], [0, 2, 0])
        self.assertEqual([(s.ref.shot, s.ref.source) for s in revision.samples], [(1, 'bench/1'), (2, 'bench/2'), (3, 'bench/3')])
        self.assertEqual(load_revision(self.revisions, revision.revision_id), revision)

    def test_fractional_scale_round_trips(self):
        plan, samples = input_for((0, 1, 0), (3,))
        frozen = freeze(self.revisions, plan, Calibration('1/3'), samples)
        reopened = self.open_store(RevisionStore, self.source_path)
        loaded = load_revision(reopened, frozen.revision_id)
        self.assertEqual(loaded.calibration.ratio, Fraction(1, 3))
        self.assertEqual([entry.kn for entry in loaded.samples], [0, Fraction(1, 3), 0])
        middle = loaded.samples[1]
        self.assertEqual((middle.kn.numerator, middle.kn.denominator, middle.ref.shot, middle.ref.source), (1, 3, 2, 'bench/2'))

    def test_missing_shot_never_freezes(self):
        with self.assertRaisesRegex(ValueError, 'expected shot 2'):
            freeze(self.revisions, self.plan, Calibration(2), self.samples[::2])
        self.assertEqual(self.revisions.count(), 0)
        frozen = freeze(self.revisions, self.plan, Calibration(2), self.samples)
        self.assertEqual(load_revision(self.revisions, frozen.revision_id), frozen)
        self.assertEqual(self.revisions.count(), 1)

    def test_duplicate_shot_never_freezes(self):
        with self.assertRaisesRegex(ValueError, 'expected shot 3'):
            freeze(self.revisions, self.plan, Calibration(2), (*self.samples[:2], self.samples[1]))
        self.assertEqual(self.revisions.count(), 0)

    def test_overlapping_partition_never_freezes(self):
        plan = TrialPlan('cy-17', (SegmentSpec('morning', 1, 2), SegmentSpec('evening', 2, 3)))
        with self.assertRaisesRegex(ValueError, 'expected segment to start at shot 3'):
            freeze(self.revisions, plan, Calibration(2), self.samples)
        self.assertEqual(self.revisions.count(), 0)

    def test_missing_measurements_and_invalid_exact_inputs(self):
        for invalid in (None, (), (RawSample(1, None, 'bench/1'),), (RawSample(1, '1/0', 'bench/1'),),
                        (RawSample(1, 1, ''),)):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                freeze(self.revisions, self.plan, Calibration(2), invalid)
        for ratio in (None, 0.25, True, 'missing'):
            with self.subTest(ratio=ratio), self.assertRaises(ValueError):
                Calibration(ratio)
        self.assertEqual(self.revisions.count(), 0)
