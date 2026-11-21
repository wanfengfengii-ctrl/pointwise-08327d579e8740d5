import json

from archive.reports import read, read_work


def export_report(store, report_id):
    return json.dumps(read(store, report_id).to_data(), ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def export_work_report(store, report_id):
    return json.dumps(read_work(store, report_id).to_data(), ensure_ascii=False, sort_keys=True, separators=(',', ':'))
