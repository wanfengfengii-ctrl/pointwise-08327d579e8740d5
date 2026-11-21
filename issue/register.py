import sqlite3

from issue.codec import V1Piece, encode_piece
from issue.evidence import build_evidence
from issue.provenance import bind_provenance
from issue.segments import select_segment
from issue.work_codec import V2Piece, encode_work_piece
from issue.work_evidence import build_work_evidence
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

    def _record_wire(self, origin, piece_id, wire):
        with self._db:
            self._db.execute('''
                INSERT INTO issued_pieces (revision_id, segment_id, piece_id, wire)
                VALUES (?, ?, ?, ?) ON CONFLICT(revision_id, segment_id) DO NOTHING
            ''', (origin.revision_id, origin.segment_id, piece_id, wire))
            fixed = self.load_wire(origin.revision_id, origin.segment_id)
        return fixed

    def record(self, piece):
        return self._record_wire(piece.provenance, piece.piece_id, encode_piece(piece))

    def record_work(self, piece):
        return self._record_wire(piece.provenance, piece.piece_id, encode_work_piece(piece))

    def count(self):
        return self._db.execute('SELECT COUNT(*) FROM issued_pieces').fetchone()[0]


def issue_segment(revision_store, register: IssueRegister, revision_id, requested):
    revision = load_revision(revision_store, revision_id)
    if revision.travel is not None:
        raise ValueError('revision carries calibrated travel; use the work segment entry')
    selected = select_segment(revision, requested)
    prior = register.load_wire(revision_id, selected.spec.segment_id)
    if prior is not None:
        return prior
    evidence = build_evidence(selected.samples)
    return register.record(V1Piece(bind_provenance(selected), evidence))


def issue_work_segment(revision_store, register: IssueRegister, revision_id, requested):
    revision = load_revision(revision_store, revision_id)
    if revision.travel is None:
        raise ValueError('revision has no calibrated travel; use the V1 segment entry')
    selected = select_segment(revision, requested)
    prior = register.load_wire(revision_id, selected.spec.segment_id)
    if prior is not None:
        return prior
    offset = revision.first_shot
    spec = selected.spec
    travels = revision.travel[spec.first_shot - offset:spec.last_shot - offset + 1]
    evidence = build_work_evidence(selected.samples, travels)
    return register.record_work(V2Piece(bind_provenance(selected), evidence))
