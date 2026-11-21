import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from archive.store import ArchiveStore
from issue.register import IssueRegister, issue_segment, issue_work_segment
from receive.admission import receive_segment, receive_work_segment
from receive.coverage import ExpectedManifest
from receive.store import AdmissionStore
from trial.calibration import Calibration
from trial.plan import SegmentSpec, TrialPlan
from trial.revisions import freeze, freeze_work
from trial.samples import RawSample
from trial.store import RevisionStore


SEVEN = (0, 4, 4, 4, 1, 3, 0)
EDGES = (0, 2, 4)


def input_for(loads, cuts, trial_id='cy-17'):
    starts = (1, *(end + 1 for end in cuts[:-1]))
    return (
        TrialPlan(trial_id, tuple(SegmentSpec(f'shift-{i}', start, end)
                                  for i, (start, end) in enumerate(zip(starts, cuts), 1))),
        tuple(RawSample(shot, load, f'bench/{shot}') for shot, load in enumerate(loads, 1)),
    )


def ledger(cycles):
    return [(entry.first.shot, entry.last.shot, entry.amplitude, entry.weight) for entry in cycles]


def work_ledger(cycles):
    return [(entry.first.shot, entry.last.shot, entry.amplitude, entry.weight, entry.work)
            for entry in cycles]


class RepositoryTest(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.source_path = self.root / 'source.sqlite'
        self.center_path = self.root / 'center.sqlite'
        self.admissions = self.open_store(AdmissionStore, self.center_path)
        self.archive = self.open_store(ArchiveStore, self.center_path)

    def open_store(self, kind, path):
        store = kind(path)
        self.addCleanup(store.close)
        store.initialize()
        return store

    def issue(self, loads=SEVEN, cuts=(3, 6, 7), ratio=1):
        plan, samples = input_for(loads, cuts)
        with closing(RevisionStore(self.source_path)) as revisions, closing(IssueRegister(self.source_path)) as register:
            revisions.initialize()
            register.initialize()
            revision = freeze(revisions, plan, Calibration(ratio), samples)
            wires = tuple(issue_segment(revisions, register, revision.revision_id, spec) for spec in revision.plan.segments)
        return revision, wires

    def issue_work(self, loads, travels, cuts, ratio=1, trial_id='cy-17'):
        plan, samples = input_for(loads, cuts, trial_id)
        travel = {shot: value for shot, value in enumerate(travels, 1)}
        with closing(RevisionStore(self.source_path)) as revisions, closing(IssueRegister(self.source_path)) as register:
            revisions.initialize()
            register.initialize()
            revision = freeze_work(revisions, plan, Calibration(ratio), samples, travel)
            wires = tuple(issue_work_segment(revisions, register, revision.revision_id, spec)
                          for spec in revision.plan.segments)
        return revision, wires

    def register(self, revision):
        return self.admissions.register_manifest(ExpectedManifest.from_revision(revision))

    def ready(self, loads=SEVEN, cuts=(3, 6, 7), ratio=1):
        revision, wires = self.issue(loads, cuts, ratio)
        manifest_id = self.register(revision)
        for wire in reversed(wires):
            receive_segment(self.admissions, manifest_id, wire)
        return revision, manifest_id, wires

    def ready_work(self, loads, travels, cuts, ratio=1, trial_id='cy-17'):
        revision, wires = self.issue_work(loads, travels, cuts, ratio, trial_id)
        manifest_id = self.register(revision)
        for wire in reversed(wires):
            receive_work_segment(self.admissions, manifest_id, wire)
        return revision, manifest_id, wires
