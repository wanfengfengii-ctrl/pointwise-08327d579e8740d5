import sqlite3
from contextlib import contextmanager


class ArchiveStore:
    def __init__(self, path):
        self._db = sqlite3.connect(path)
        self._db.row_factory = sqlite3.Row
        self._db.execute('PRAGMA foreign_keys = ON')

    def close(self):
        self._db.close()

    def initialize(self):
        with self.publication_transaction() as connection:
            connection.execute('''
                CREATE TABLE IF NOT EXISTS published_reports (
                    report_id INTEGER PRIMARY KEY,
                    manifest_id TEXT NOT NULL,
                    trial_id TEXT NOT NULL,
                    revision_id TEXT NOT NULL,
                    detail TEXT NOT NULL,
                    UNIQUE (report_id, manifest_id)
                )
            ''')
            connection.execute('''
                CREATE TABLE IF NOT EXISTS publication_receipts (
                    receipt_id INTEGER PRIMARY KEY,
                    report_id INTEGER NOT NULL UNIQUE,
                    manifest_id TEXT NOT NULL,
                    FOREIGN KEY (report_id, manifest_id)
                        REFERENCES published_reports (report_id, manifest_id)
                )
            ''')
            connection.execute('''
                CREATE TABLE IF NOT EXISTS published_work_reports (
                    report_id INTEGER PRIMARY KEY,
                    manifest_id TEXT NOT NULL,
                    trial_id TEXT NOT NULL,
                    revision_id TEXT NOT NULL,
                    detail TEXT NOT NULL,
                    UNIQUE (report_id, manifest_id)
                )
            ''')
            connection.execute('''
                CREATE TABLE IF NOT EXISTS work_publication_receipts (
                    receipt_id INTEGER PRIMARY KEY,
                    report_id INTEGER NOT NULL UNIQUE,
                    manifest_id TEXT NOT NULL,
                    FOREIGN KEY (report_id, manifest_id)
                        REFERENCES published_work_reports (report_id, manifest_id)
                )
            ''')

    @contextmanager
    def publication_transaction(self):
        with self._db:
            self._db.execute('BEGIN IMMEDIATE')
            yield self._db

    def read_snapshot(self, report_id):
        return self._db.execute('''
            SELECT r.report_id, r.manifest_id, r.trial_id, r.revision_id, r.detail,
                   p.receipt_id, p.manifest_id AS receipt_manifest_id
            FROM published_reports AS r
            LEFT JOIN publication_receipts AS p ON p.report_id = r.report_id
            WHERE r.report_id = ?
        ''', (report_id,)).fetchone()

    def read_work_snapshot(self, report_id):
        return self._db.execute('''
            SELECT r.report_id, r.manifest_id, r.trial_id, r.revision_id, r.detail,
                   p.receipt_id, p.manifest_id AS receipt_manifest_id
            FROM published_work_reports AS r
            LEFT JOIN work_publication_receipts AS p ON p.report_id = r.report_id
            WHERE r.report_id = ?
        ''', (report_id,)).fetchone()

    def counts(self):
        row = self._db.execute('''
            SELECT (SELECT COUNT(*) FROM published_reports),
                   (SELECT COUNT(*) FROM publication_receipts)
        ''').fetchone()
        return tuple(row)

    def work_counts(self):
        row = self._db.execute('''
            SELECT (SELECT COUNT(*) FROM published_work_reports),
                   (SELECT COUNT(*) FROM work_publication_receipts)
        ''').fetchone()
        return tuple(row)
