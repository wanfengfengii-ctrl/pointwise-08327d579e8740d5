from dataclasses import dataclass
from fractions import Fraction

from trial.calibration import convert_to_kn, parse_exact


@dataclass(frozen=True)
class ShotRef:
    shot: int
    source: str

    def __post_init__(self):
        if type(self.shot) is not int:
            raise ValueError('shot number must be an integer')
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError(f'shot {self.shot} needs a source reference')

    def to_data(self):
        return {'shot': self.shot, 'source': self.source}


@dataclass(frozen=True)
class RawSample:
    shot: int
    reading: int | str | Fraction
    source: str


@dataclass(frozen=True)
class CalibratedSample:
    ref: ShotRef
    reading: Fraction
    kn: Fraction


def validate_sample_order(samples):
    if samples is None:
        raise ValueError('a trial needs at least one sample')
    ordered = tuple(samples)
    if not ordered:
        raise ValueError('a trial needs at least one sample')
    previous = None
    for sample in ordered:
        if not isinstance(sample, RawSample) or type(sample.shot) is not int:
            raise ValueError('a raw sample must have an integer shot number')
        if previous is not None and sample.shot != previous + 1:
            raise ValueError(f'expected shot {previous + 1}, got {sample.shot}')
        previous = sample.shot
    return ordered


def normalize_samples(samples, calibration):
    calibrated = []
    for sample in validate_sample_order(samples):
        ref = ShotRef(sample.shot, sample.source)
        reading = parse_exact(sample.reading)
        calibrated.append(CalibratedSample(ref, reading, convert_to_kn(reading, calibration)))
    return tuple(calibrated)
