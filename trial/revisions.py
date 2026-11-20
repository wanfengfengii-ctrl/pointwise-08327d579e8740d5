from dataclasses import dataclass

from trial.calibration import Calibration, parse_exact
from trial.plan import SegmentSpec, TrialPlan, validate_segment_plan
from trial.samples import CalibratedSample, ShotRef, normalize_samples
from trial.store import RevisionStore


@dataclass(frozen=True)
class Revision:
    revision_id: str
    plan: TrialPlan
    calibration: Calibration
    samples: tuple[CalibratedSample, ...]

    @property
    def first_shot(self):
        return self.samples[0].ref.shot

    @property
    def last_shot(self):
        return self.samples[-1].ref.shot


def freeze(store: RevisionStore, plan: TrialPlan, calibration: Calibration, samples):
    calibrated = normalize_samples(samples, calibration)
    segments = validate_segment_plan(plan.segments, calibrated[0].ref.shot, calibrated[-1].ref.shot)
    fixed_plan = TrialPlan(plan.trial_id, segments)
    snapshot = {
        'trial_id': fixed_plan.trial_id,
        'ratio': str(calibration.ratio),
        'segments': [segment.to_data() for segment in segments],
        'samples': [
            {'ref': sample.ref.to_data(), 'reading': str(sample.reading), 'kn': str(sample.kn)}
            for sample in calibrated
        ],
    }
    revision_id = store.insert_snapshot(snapshot)
    return Revision(revision_id, fixed_plan, calibration, calibrated)


def load_revision(store: RevisionStore, revision_id: str):
    snapshot = store.load_snapshot(revision_id)
    plan = TrialPlan(snapshot['trial_id'], tuple(SegmentSpec(**entry) for entry in snapshot['segments']))
    samples = tuple(
        CalibratedSample(ShotRef(**entry['ref']), parse_exact(entry['reading']), parse_exact(entry['kn']))
        for entry in snapshot['samples']
    )
    return Revision(revision_id, plan, Calibration(snapshot['ratio']), samples)
