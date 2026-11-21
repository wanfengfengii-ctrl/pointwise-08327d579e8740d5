import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class PublicationReceipt:
    receipt_id: int
    report_id: int
    manifest_id: str

    def to_data(self):
        return {'receipt_id': self.receipt_id, 'report_id': self.report_id, 'manifest_id': self.manifest_id}


def store_receipt(connection: sqlite3.Connection, report_id, manifest_id):
    cursor = connection.execute('''
        INSERT INTO publication_receipts (report_id, manifest_id) VALUES (?, ?)
    ''', (report_id, manifest_id))
    return PublicationReceipt(cursor.lastrowid, report_id, manifest_id)


def store_work_receipt(connection: sqlite3.Connection, report_id, manifest_id):
    cursor = connection.execute('''
        INSERT INTO work_publication_receipts (report_id, manifest_id) VALUES (?, ?)
    ''', (report_id, manifest_id))
    return PublicationReceipt(cursor.lastrowid, report_id, manifest_id)


def load_receipt(snapshot: sqlite3.Row):
    if snapshot['receipt_id'] is None or snapshot['receipt_manifest_id'] != snapshot['manifest_id']:
        raise RuntimeError('stored report has no corresponding success receipt')
    return PublicationReceipt(snapshot['receipt_id'], snapshot['report_id'], snapshot['receipt_manifest_id'])
