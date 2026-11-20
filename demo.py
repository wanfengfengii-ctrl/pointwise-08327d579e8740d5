import argparse
import json
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from archive.export import export_report
from archive.publication import publish
from archive.reports import read
from archive.store import ArchiveStore
from issue.register import IssueRegister, issue_segment
from receive.admission import receive_segment
from receive.coverage import ExpectedManifest
from receive.store import AdmissionStore
from trial.calibration import Calibration
from trial.plan import SegmentSpec, TrialPlan
from trial.revisions import freeze
from trial.samples import RawSample
from trial.store import RevisionStore


def run_demo(sample_path, workdir):
    sample = json.loads(sample_path.read_text(encoding='utf-8'))
    plan = TrialPlan(sample['trial_id'], tuple(SegmentSpec(**entry) for entry in sample['segments']))
    source_path = workdir / 'source.sqlite'
    center_path = workdir / 'center.sqlite'
    with closing(RevisionStore(source_path)) as revisions, closing(IssueRegister(source_path)) as register:
        revisions.initialize()
        register.initialize()
        revision = freeze(revisions, plan, Calibration(sample['ratio']), (RawSample(**row) for row in sample['samples']))
        expected_manifest = ExpectedManifest.from_revision(revision)
        packets = {entry.segment_id: issue_segment(revisions, register, revision.revision_id, entry)
                   for entry in revision.plan.segments}

    with closing(AdmissionStore(center_path)) as admissions, closing(ArchiveStore(center_path)) as archive:
        admissions.initialize()
        archive.initialize()
        manifest_id = admissions.register_manifest(expected_manifest)
        arrivals = [receive_segment(admissions, manifest_id, packets[key]) for key in sample['arrival']]
        signed = publish(admissions, archive, manifest_id, sample['band_edges'])

    with closing(ArchiveStore(center_path)) as reopened:
        report_id = signed.report.report_id
        retrieved = read(reopened, report_id)
        exported = json.loads(export_report(reopened, report_id))

    actual = [[entry.first.shot, entry.last.shot, str(entry.amplitude), str(entry.weight)]
              for entry in retrieved.report.cycles]
    receipt = retrieved.receipt
    downstream = {
        'arrival_ready': [arrival.status.ready for arrival in arrivals],
        'band_counts': [str(band.count) for band in retrieved.report.bands],
        'parent_segments': [parent.segment_id for parent in retrieved.report.parents],
        'receipt_matches': receipt.report_id == report_id and receipt.manifest_id == manifest_id,
        'reopened_export_matches': retrieved == signed and exported == signed.to_data(),
    }
    if actual != sample['expected_cycles'] or downstream != sample['expected_downstream']:
        raise AssertionError(f'v6 whole-trial ledger differs: cycles={actual!r}, downstream={downstream!r}')
    return {
        'case_id': 'v6',
        'input': {name: sample[name] for name in ('trial_id', 'ratio', 'samples', 'segments', 'arrival', 'band_edges')},
        'expected': sample['expected_cycles'],
        'actual': actual,
        'downstream_expected': sample['expected_downstream'],
        'downstream_actual': downstream,
        'code_paths': ['issue/evidence.py', 'receive/admission.py', 'wear/turns.py', 'wear/cycles.py',
                       'wear/bands.py', 'archive/publication.py', 'archive/export.py'],
        'oracle': '手算转折拍 1、4、5、6、7。四点拍 4、5、6、7 夹住幅值 2 kN，余下两个 4 kN 半循环。按区间边界和精确计数求得 0、1、1。',
    }


def main():
    parser = argparse.ArgumentParser(description='Run the seven-shot offline wear ledger demonstration')
    parser.add_argument('sample', type=Path)
    arguments = parser.parse_args()
    with TemporaryDirectory(prefix='wear-ledger-') as directory:
        scenario = run_demo(arguments.sample, Path(directory))
    print('POINTWISE_SCENARIO ' + json.dumps(scenario, ensure_ascii=False, separators=(',', ':')))


if __name__ == '__main__':
    main()
