import sqlite3

from issue.codec import V1Piece, encode_piece
from issue.evidence import build_evidence
from issue.provenance import bind_provenance
from issue.segments import select_segment
from trial.revisions import load_revision


class IssueRegister:
    def __init__(self, path):
        self._db = sqlite3.connect(path)

    def close(self):
        self._db.close()

    def initialize(self):
        with self._db:
            self._db.execute('''
                CREATE TABLE IF NOT EXISTS issued_pieces (
                    revision_id TEXT NOT NULL,
                    segment_id TEXT NOT NULL,
                    piece_id TEXT NOT NULL UNIQUE,
                    wire TEXT NOT NULL,
                    PRIMARY KEY (revision_id, segment_id)
                )
            ''')

    def load_wire(self, revision_id, segment_id):
        row = self._db.execute(
            'SELECT wire FROM issued_pieces WHERE revision_id = ? AND segment_id = ?',
            (revision_id, segment_id),
        ).fetchone()
        return None if row is None else row[0]

    def record(self, piece):
        origin = piece.provenance
        wire = encode_piece(piece)
        with self._db:
            self._db.execute('''
                INSERT INTO issued_pieces (revision_id, segment_id, piece_id, wire)
                VALUES (?, ?, ?, ?) ON CONFLICT(revision_id, segment_id) DO NOTHING
            ''', (origin.revision_id, origin.segment_id, piece.piece_id, wire))
            fixed = self.load_wire(origin.revision_id, origin.segment_id)
        return fixed

    def count(self):
        return self._db.execute('SELECT COUNT(*) FROM issued_pieces').fetchone()[0]


def issue_segment(revision_store, register: IssueRegister, revision_id, requested):
    selected = select_segment(load_revision(revision_store, revision_id), requested)
    prior = register.load_wire(revision_id, selected.spec.segment_id)
    if prior is not None:
        return prior
    evidence = build_evidence(selected.samples)
    return register.record(V1Piece(bind_provenance(selected), evidence))
