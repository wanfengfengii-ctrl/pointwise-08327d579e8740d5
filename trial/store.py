import hashlib
import json
import sqlite3


class RevisionStore:
    def __init__(self, path):
        self._db = sqlite3.connect(path)

    def close(self):
        self._db.close()

    def initialize(self):
        with self._db:
            self._db.execute('''
                CREATE TABLE IF NOT EXISTS revisions (
                    sequence INTEGER PRIMARY KEY,
                    revision_id TEXT NOT NULL UNIQUE,
                    snapshot TEXT NOT NULL
                )
            ''')

    def insert_snapshot(self, snapshot):
        document = json.dumps(snapshot, sort_keys=True, separators=(',', ':'))
        with self._db:
            self._db.execute('BEGIN IMMEDIATE')
            sequence = self._db.execute('SELECT COALESCE(MAX(sequence), 0) + 1 FROM revisions').fetchone()[0]
            identity = hashlib.sha256(f'{sequence}\n{document}'.encode('utf-8')).hexdigest()
            self._db.execute(
                'INSERT INTO revisions (sequence, revision_id, snapshot) VALUES (?, ?, ?)',
                (sequence, identity, document),
            )
        return identity

    def load_snapshot(self, revision_id):
        row = self._db.execute('SELECT snapshot FROM revisions WHERE revision_id = ?', (revision_id,)).fetchone()
        if row is None:
            raise KeyError(revision_id)
        return json.loads(row[0])

    def count(self):
        return self._db.execute('SELECT COUNT(*) FROM revisions').fetchone()[0]
