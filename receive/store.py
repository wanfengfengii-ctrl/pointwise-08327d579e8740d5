import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass

from receive.coverage import ExpectedManifest
from receive.identity import ReceiptIdentity


@dataclass(frozen=True)
class StoredPiece:
    identity: ReceiptIdentity
    wire: str


class AdmissionStore:
    def __init__(self, path):
        self._db = sqlite3.connect(path)
        self._db.execute('PRAGMA foreign_keys = ON')

    def close(self):
        self._db.close()

    def initialize(self):
        with self.receipt_transaction() as connection:
            connection.execute('''
                CREATE TABLE IF NOT EXISTS expected_manifests (
                    manifest_id TEXT PRIMARY KEY NOT NULL,
                    trial_id TEXT NOT NULL,
                    revision_id TEXT NOT NULL,
                    body TEXT NOT NULL,
                    UNIQUE (trial_id, revision_id)
                )
            ''')
            connection.execute('''
                CREATE TABLE IF NOT EXISTS received_pieces (
                    manifest_id TEXT NOT NULL REFERENCES expected_manifests(manifest_id),
                    segment_id TEXT NOT NULL,
                    piece_id TEXT NOT NULL,
                    receipt_id TEXT NOT NULL UNIQUE,
                    wire TEXT NOT NULL,
                    PRIMARY KEY (manifest_id, segment_id),
                    UNIQUE (manifest_id, piece_id)
                )
            ''')

    @contextmanager
    def receipt_transaction(self):
        with self._db:
            self._db.execute('BEGIN IMMEDIATE')
            yield self._db

    def register_manifest(self, expected: ExpectedManifest):
        manifest_id = expected.manifest_id
        body = expected.to_json()
        with self.receipt_transaction() as connection:
            connection.execute('''
                INSERT INTO expected_manifests (manifest_id, trial_id, revision_id, body)
                VALUES (?, ?, ?, ?) ON CONFLICT(trial_id, revision_id) DO NOTHING
            ''', (manifest_id, expected.trial_id, expected.revision_id, body))
            stored = connection.execute('''
                SELECT manifest_id, body FROM expected_manifests WHERE trial_id = ? AND revision_id = ?
            ''', (expected.trial_id, expected.revision_id)).fetchone()
            if stored != (manifest_id, body):
                raise ValueError('revision already has a different registered manifest')
        return manifest_id

    def record_piece(self, connection, identity, wire):
        connection.execute('''
            INSERT INTO received_pieces (manifest_id, segment_id, piece_id, receipt_id, wire)
            VALUES (?, ?, ?, ?, ?)
        ''', (identity.manifest_id, identity.segment_id, identity.piece_id, identity.receipt_id, wire))

    def read_manifest_snapshot(self, manifest_id):
        rows = self._db.execute('''
            SELECT m.body, p.segment_id, p.piece_id, p.receipt_id, p.wire
            FROM expected_manifests AS m
            LEFT JOIN received_pieces AS p ON p.manifest_id = m.manifest_id
            WHERE m.manifest_id = ?
        ''', (manifest_id,)).fetchall()
        if not rows:
            raise KeyError(manifest_id)
        expected = ExpectedManifest.from_json(rows[0][0])
        if expected.manifest_id != manifest_id:
            raise RuntimeError('stored manifest identity disagrees with its plan')
        pieces = tuple(
            StoredPiece(ReceiptIdentity(manifest_id, segment_id, piece_id, receipt_id), wire)
            for _, segment_id, piece_id, receipt_id, wire in rows if segment_id is not None
        )
        return expected, pieces
