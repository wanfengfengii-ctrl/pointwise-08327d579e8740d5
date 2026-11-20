from dataclasses import dataclass
from fractions import Fraction

from trial.samples import ShotRef
from wear.turns import Turn


@dataclass(frozen=True)
class Cycle:
    first: ShotRef
    last: ShotRef
    amplitude: Fraction
    weight: Fraction

    def to_data(self):
        return {
            'first': self.first.to_data(),
            'last': self.last.to_data(),
            'amplitude': str(self.amplitude),
            'weight': str(self.weight),
        }

    @classmethod
    def from_data(cls, data):
        return cls(ShotRef(**data['first']), ShotRef(**data['last']), Fraction(data['amplitude']), Fraction(data['weight']))


def count_cycles(turns: tuple[Turn, ...]):
    remaining = list(turns)
    cycles = []
    while len(remaining) >= 4:
        for index in range(len(remaining) - 3):
            left, first, last, right = remaining[index:index + 4]
            amplitude = abs(last.kn - first.kn)
            if 0 < amplitude <= min(abs(first.kn - left.kn), abs(right.kn - last.kn)):
                cycles.append(Cycle(first.ref, last.ref, amplitude, Fraction(1)))
                del remaining[index + 1:index + 3]
                break
        else:
            break
    for first, last in zip(remaining, remaining[1:]):
        amplitude = abs(last.kn - first.kn)
        if amplitude > 0:
            cycles.append(Cycle(first.ref, last.ref, amplitude, Fraction(1, 2)))
    return tuple(cycles)
