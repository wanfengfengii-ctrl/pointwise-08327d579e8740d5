from dataclasses import dataclass
from fractions import Fraction

from receive.manifest import AcceptedManifest, IncompleteManifest
from wear.bands import BandTotal, summarize_bands, validate_band_edges
from wear.cycles import Cycle, count_cycles
from wear.turns import Turn, restore_turns


@dataclass(frozen=True)
class AssessmentResult:
    turns: tuple[Turn, ...]
    cycles: tuple[Cycle, ...]
    band_edges: tuple[Fraction, ...]
    bands: tuple[BandTotal, ...]


def assess(manifest: AcceptedManifest, band_edges):
    if not manifest.status.ready:
        raise IncompleteManifest(f'missing segments: {manifest.status.missing!r}')
    edges = validate_band_edges(band_edges)
    turns = restore_turns(entry.piece.evidence for entry in manifest.entries)
    cycles = count_cycles(turns)
    return AssessmentResult(turns, cycles, edges, summarize_bands(cycles, edges))
