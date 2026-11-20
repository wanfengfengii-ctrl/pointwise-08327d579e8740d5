from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from demo import run_demo


class WorkflowTests(unittest.TestCase):
    def test_daily_offline_signing_and_historical_export(self):
        sample = Path(__file__).resolve().parents[1] / 'samples' / 'seven_shots.json'
        with TemporaryDirectory() as directory:
            scenario = run_demo(sample, Path(directory))
        self.assertEqual(scenario['case_id'], 'v6')
        self.assertEqual(scenario['input']['arrival'], ['shift-3', 'shift-1', 'shift-2'])
        self.assertEqual(scenario['actual'], [[5, 6, '2', '1'], [1, 4, '4', '1/2'], [4, 7, '4', '1/2']])
        self.assertEqual(scenario['downstream_actual'], {
            'arrival_ready': [False, False, True],
            'band_counts': ['0', '1', '1'],
            'parent_segments': ['shift-1', 'shift-2', 'shift-3'],
            'receipt_matches': True,
            'reopened_export_matches': True,
        })
