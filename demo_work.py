import argparse
import json
from contextlib import closing
from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory

from archive.export import export_work_report
from archive.publication import publish_work
from archive.reports import read_work
from archive.store import ArchiveStore
from issue.register import IssueRegister, issue_work_segment
from receive.admission import receive_work_segment
from receive.coverage import ExpectedManifest
from receive.store import AdmissionStore
from trial.calibration import Calibration
from trial.plan import SegmentSpec, TrialPlan
from trial.revisions import freeze_work
from trial.samples import RawSample
from trial.store import RevisionStore


def plan_for(trial_id, endings):
    starts = (1, *(end + 1 for end in endings[:-1]))
    return TrialPlan(trial_id, tuple(SegmentSpec(f'shift-{index}', start, end)
                                     for index, (start, end) in enumerate(zip(starts, endings), 1)))


def run_work_case(case, endings, workdir):
    """Freeze with calibrated travel, issue V2 pieces, then close the source before
    the offline center receives them out of order, signs the work ledger and is
    reopened for retrieval. Reopening the source re-issues the same fixed bytes."""
    plan = plan_for(case['trial_id'], endings)
    samples = tuple(RawSample(row['shot'], row['reading'], row['source']) for row in case['samples'])
    travel = {row['shot']: row['travel_mm'] for row in case['samples']}
    source_path = workdir / 'source.sqlite'
    center_path = workdir / 'center.sqlite'
    with closing(RevisionStore(source_path)) as revisions, closing(IssueRegister(source_path)) as register:
        revisions.initialize()
        register.initialize()
        revision = freeze_work(revisions, plan, Calibration(case['ratio']), samples, travel)
        expected_manifest = ExpectedManifest.from_revision(revision)
        packets = {spec.segment_id: issue_work_segment(revisions, register, revision.revision_id, spec)
                   for spec in revision.plan.segments}

    with closing(AdmissionStore(center_path)) as admissions, closing(ArchiveStore(center_path)) as archive:
        admissions.initialize()
        archive.initialize()
        manifest_id = admissions.register_manifest(expected_manifest)
        segment_ids = [spec.segment_id for spec in revision.plan.segments]
        arrivals = [receive_work_segment(admissions, manifest_id, packets[key]) for key in reversed(segment_ids)]
        signed = publish_work(admissions, archive, manifest_id, case['band_edges'])

    with closing(RevisionStore(source_path)) as revisions, closing(IssueRegister(source_path)) as register:
        revisions.initialize()
        register.initialize()
        reissued = {spec.segment_id: issue_work_segment(revisions, register, revision.revision_id, spec)
                    for spec in revision.plan.segments}

    with closing(ArchiveStore(center_path)) as reopened:
        report_id = signed.report.report_id
        retrieved = read_work(reopened, report_id)
        exported = json.loads(export_work_report(reopened, report_id))

    report = retrieved.report
    cycles = [[entry.first.shot, entry.last.shot, str(entry.amplitude), str(entry.weight), str(entry.work)]
              for entry in report.cycles]
    complete_work = sum((entry.work for entry in report.cycles if entry.weight == 1), Fraction(0))
    downstream = {
        'arrival_ready': [arrival.status.ready for arrival in arrivals],
        'band_counts': [str(band.count) for band in report.bands],
        'parent_segments': [parent.segment_id for parent in report.parents],
        'total_work_j': str(report.total_work),
        'remaining_work_j': str(report.remaining_work),
        'complete_plus_remaining_is_total': complete_work + report.remaining_work == report.total_work,
        'reissued_matches': reissued == packets,
        'receipt_matches': retrieved.receipt.report_id == report_id and retrieved.receipt.manifest_id == manifest_id,
        'reopened_export_matches': retrieved == signed and exported == signed.to_data(),
    }
    expected = case['expected']
    expected_downstream = {
        'band_counts': expected['band_counts'],
        'total_work_j': expected['total_work_j'],
        'remaining_work_j': expected['remaining_work_j'],
    }
    actual_downstream = {key: downstream[key] for key in expected_downstream}
    if cycles != expected['cycles'] or actual_downstream != expected_downstream or not all(downstream.values()):
        raise AssertionError(f'work ledger differs: cycles={cycles!r}, downstream={downstream!r}')
    return {
        'case_id': case['case_id'],
        'segment_endings': list(endings),
        'expected': expected['cycles'],
        'actual': cycles,
        'downstream_expected': expected_downstream,
        'downstream_actual': actual_downstream,
        'downstream_checks': downstream,
    }


def run_work_cases(sample_path, workdir_root):
    cases = json.loads(sample_path.read_text(encoding='utf-8'))['cases']
    scenarios = []
    for case_index, case in enumerate(cases):
        for group_index, endings in enumerate(case['segment_endings']):
            workdir = workdir_root / f'case-{case_index}-{group_index}'
            workdir.mkdir()
            scenarios.append(run_work_case(case, tuple(endings), workdir))
    return scenarios


def main():
    parser = argparse.ArgumentParser(description='Run the offline signed-travel work ledger demonstration')
    parser.add_argument('sample', type=Path)
    arguments = parser.parse_args()
    with TemporaryDirectory(prefix='wear-work-ledger-') as directory:
        scenarios = run_work_cases(arguments.sample, Path(directory))
    scenario = {
        'case_id': 'v7-work',
        'scenarios': scenarios,
        'code_paths': ['trial/revisions.py', 'issue/work_evidence.py', 'issue/work_codec.py',
                       'receive/work_identity.py', 'receive/admission.py', 'wear/work.py',
                       'archive/publication.py', 'archive/reports.py', 'archive/export.py'],
        'oracle': '手算八拍原路径做功 38 J。四点窗口先消拍 4、6 记 1/2 J，再消拍 3、7 记 −2 J，'
                  '余路径 79/2 J 归半循环；完整循环做功加余路径恒等于整轮。',
    }
    print('POINTWISE_SCENARIO ' + json.dumps(scenario, ensure_ascii=False, separators=(',', ':')))


if __name__ == '__main__':
    main()
