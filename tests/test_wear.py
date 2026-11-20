from fractions import Fraction

from receive.manifest import require_ready_manifest
from tests import EDGES, SEVEN, RepositoryTest, ledger
from wear.assessment import assess


HALF = Fraction(1, 2)
SEVEN_LEDGER = [(5, 6, 2, 1), (1, 4, 4, HALF), (4, 7, 4, HALF)]


class WearTests(RepositoryTest):
    def assess_loads(self, loads, cuts, edges=EDGES, ratio=1):
        _, manifest_id, _ = self.ready(loads, cuts, ratio)
        return assess(require_ready_manifest(self.admissions, manifest_id), edges)

    def test_seven_shot_split_matches_whole_trial(self):
        split = self.assess_loads(SEVEN, (3, 6, 7))
        whole = self.assess_loads(SEVEN, (7,))
        self.assertEqual(split, whole)
        self.assertEqual(ledger(split.cycles), SEVEN_LEDGER, 'seven-shot whole-trial ledger')
        self.assertEqual([(turn.ref.shot, turn.kn) for turn in split.turns], [(1, 0), (4, 4), (5, 1), (6, 3), (7, 0)])
        self.assertEqual([(cycle.first.source, cycle.last.source) for cycle in split.cycles],
                         [('bench/5', 'bench/6'), ('bench/1', 'bench/4'), ('bench/4', 'bench/7')])

    def test_single_shot_bridge_in_reverse_arrival_order(self):
        result = self.assess_loads(SEVEN, (2, 3, 4, 6, 7))
        self.assertEqual(ledger(result.cycles), SEVEN_LEDGER)
        self.assertEqual(result.turns[1].ref.source, 'bench/4')
        self.assertEqual([band.count for band in result.bands], [0, 1, 1])

    def test_plateau_continues_across_leading_seam(self):
        result = self.assess_loads((0, 4, 4, 4, 2, 0), (2, 6))
        self.assertEqual(ledger(result.cycles), [(1, 4, 4, HALF), (4, 6, 4, HALF)])
        self.assertEqual([turn.ref.shot for turn in result.turns], [1, 4, 6])

    def test_monotone_join_drops_both_seam_anchors(self):
        result = self.assess_loads((0, 1, 2, 3), (2, 4))
        self.assertEqual([turn.ref.shot for turn in result.turns], [1, 4])
        self.assertEqual(ledger(result.cycles), [(1, 4, 3, HALF)])

    def test_trial_boundary_plateaus_keep_actual_first_and_last(self):
        result = self.assess_loads((2, 2, 4, 4, 2, 2), (1, 3, 5, 6))
        self.assertEqual([turn.ref.shot for turn in result.turns], [1, 4, 6])
        self.assertEqual(ledger(result.cycles), [(1, 4, 2, HALF), (4, 6, 2, HALF)])

    def test_leftmost_eligible_window_is_eliminated_first(self):
        result = self.assess_loads((0, 4, 2, 4, 2, 4, 0), (2, 5, 7))
        self.assertEqual(ledger(result.cycles), [(2, 3, 2, 1), (4, 5, 2, 1), (1, 6, 4, HALF), (6, 7, 4, HALF)])

    def test_band_edges_are_left_closed_and_zero_is_implicit(self):
        explicit = self.assess_loads(SEVEN, (3, 6, 7))
        implicit = self.assess_loads(SEVEN, (3, 6, 7), (2, 4))
        self.assertEqual(implicit, explicit)
        self.assertEqual([(band.lower, band.upper, band.count) for band in explicit.bands],
                         [(0, 2, 0), (2, 4, 1), (4, None, 1)])

    def test_fractional_cutpoint_owns_equal_amplitude(self):
        result = self.assess_loads((0, 1, 0), (1, 3), (0, '1/3'), '1/3')
        self.assertEqual(ledger(result.cycles), [(1, 2, Fraction(1, 3), HALF), (2, 3, Fraction(1, 3), HALF)])
        self.assertEqual([(band.lower, band.upper, band.count) for band in result.bands],
                         [(0, Fraction(1, 3), 0), (Fraction(1, 3), None, 1)])

    def test_all_flat_two_segments(self):
        result = self.assess_loads((4, 4, 4, 4), (2, 4))
        self.assertEqual([(turn.ref.shot, turn.kn) for turn in result.turns], [(1, 4), (4, 4)])
        self.assertEqual(result.cycles, ())
        self.assertEqual([band.count for band in result.bands], [0, 0, 0])

    def test_single_shot_has_no_cycles(self):
        result = self.assess_loads((4,), (1,))
        self.assertEqual([(turn.ref.shot, turn.kn) for turn in result.turns], [(1, 4)])
        self.assertEqual(result.cycles, ())
        self.assertEqual([band.count for band in result.bands], [0, 0, 0])
