from dataclasses import dataclass
from fractions import Fraction


def parse_exact(value):
    if type(value) is int or isinstance(value, (str, Fraction)):
        try:
            return Fraction(value)
        except (ValueError, ZeroDivisionError) as error:
            raise ValueError(f'invalid rational value {value!r}') from error
    raise ValueError(f'expected an integer, rational string or Fraction, got {value!r}')


@dataclass(frozen=True)
class Calibration:
    ratio: Fraction

    def __post_init__(self):
        object.__setattr__(self, 'ratio', parse_exact(self.ratio))


def convert_to_kn(reading, calibration):
    return parse_exact(reading) * calibration.ratio
