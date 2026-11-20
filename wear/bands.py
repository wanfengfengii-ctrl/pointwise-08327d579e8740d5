from bisect import bisect_right
from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction

from trial.calibration import parse_exact
from wear.cycles import Cycle


@dataclass(frozen=True)
class BandTotal:
    lower: Fraction
    upper: Fraction | None
    count: Fraction

    def to_data(self):
        return {'lower': str(self.lower), 'upper': None if self.upper is None else str(self.upper), 'count': str(self.count)}

    @classmethod
    def from_data(cls, data):
        upper = None if data['upper'] is None else Fraction(data['upper'])
        return cls(Fraction(data['lower']), upper, Fraction(data['count']))


def validate_band_edges(edges):
    if isinstance(edges, (str, bytes, bytearray, Mapping)):
        raise ValueError('band edges must be a collection of exact values')
    try:
        parsed = tuple(parse_exact(edge) for edge in edges)
    except TypeError as error:
        raise ValueError('band edges must be a collection of exact values') from error
    if not parsed or parsed[0] < 0 or any(left >= right for left, right in zip(parsed, parsed[1:])):
        raise ValueError('band edges must be nonnegative and strictly increasing')
    if parsed[0] > 0:
        return (Fraction(0), *parsed)
    return parsed


def summarize_bands(cycles: tuple[Cycle, ...], edges: tuple[Fraction, ...]):
    """Accumulate cycle weights using normalized lower bounds."""
    counts = [Fraction(0) for _ in edges]
    for cycle in cycles:
        slot = bisect_right(edges, cycle.amplitude) - 1
        counts[slot] += cycle.weight
    return tuple(BandTotal(low, high, count) for low, high, count in zip(edges, (*edges[1:], None), counts))
