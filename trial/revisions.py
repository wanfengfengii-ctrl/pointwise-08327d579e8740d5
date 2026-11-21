from collections.abc import Mapping
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
    travel: tuple | None = None

    @property
    def first_shot(self):
        return self.samples[0].ref.shot

    @property
    def last_shot(self):
        return self.samples[-1].ref.shot


def _samples_snapshot(calibrated):
    return [
        {'ref': sample.ref.to_data(), 'reading': str(sample.reading), 'kn': str(sample.kn)}
        for sample in calibrated
    ]


def freeze(store: RevisionStore, plan: TrialPlan, calibration: Calibration, samples):
    calibrated = normalize_samples(samples, calibration)
    segments = validate_segment_plan(plan.segments, calibrated[0].ref.shot, calibrated[-1].ref.shot)
    fixed_plan = TrialPlan(plan.trial_id, segments)
    snapshot = {
        'trial_id': fixed_plan.trial_id,
        'ratio': str(calibration.ratio),
        'segments': [segment.to_data() for segment in segments],
        'samples': _samples_snapshot(calibrated),
    }
    revision_id = store.insert_snapshot(snapshot)
    return Revision(revision_id, fixed_plan, calibration, calibrated)


def _normalize_travel(travel_mm, calibrated):
    if not isinstance(travel_mm, Mapping):
        raise ValueError('travel_mm must map integer shot numbers to exact readings')
    shots = tuple(sample.ref.shot for sample in calibrated)
    if len(travel_mm) != len(shots):
        raise ValueError('travel_mm must cover exactly every frozen shot')
    travel = {}
    for key, value in travel_mm.items():
        if type(key) is not int:
            raise ValueError('travel_mm keys must be integer shot numbers')
        travel[key] = parse_exact(value)
    if set(travel) != set(shots):
        raise ValueError('travel_mm must cover exactly every frozen shot')
    return tuple(travel[shot] for shot in shots)


def freeze_work(store: RevisionStore, plan: TrialPlan, calibration: Calibration, samples, travel_mm):
    calibrated = normalize_samples(samples, calibration)
    travel = _normalize_travel(travel_mm, calibrated)
    segments = validate_segment_plan(plan.segments, calibrated[0].ref.shot, calibrated[-1].ref.shot)
    fixed_plan = TrialPlan(plan.trial_id, segments)
    snapshot = {
        'trial_id': fixed_plan.trial_id,
        'ratio': str(calibration.ratio),
        'segments': [segment.to_data() for segment in segments],
        'samples': _samples_snapshot(calibrated),
        'travel_mm': {str(sample.ref.shot): str(value) for sample, value in zip(calibrated, travel)},
    }
    revision_id = store.insert_snapshot(snapshot)
    return Revision(revision_id, fixed_plan, calibration, calibrated, travel)


def load_revision(store: RevisionStore, revision_id: str):
    snapshot = store.load_snapshot(revision_id)
    plan = TrialPlan(snapshot['trial_id'], tuple(SegmentSpec(**entry) for entry in snapshot['segments']))
    samples = tuple(
        CalibratedSample(ShotRef(**entry['ref']), parse_exact(entry['reading']), parse_exact(entry['kn']))
        for entry in snapshot['samples']
    )
    stored_travel = snapshot.get('travel_mm')
    travel = None
    if stored_travel is not None:
        travel = tuple(parse_exact(stored_travel[str(sample.ref.shot)]) for sample in samples)
    return Revision(revision_id, plan, Calibration(snapshot['ratio']), samples, travel)
