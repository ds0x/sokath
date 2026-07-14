"""Versioned shorthand corpus.

Every entry carries full provenance: who proposed it, who ratified it,
and every revision triggered by a repair event. The corpus IS the audit log.
"""
from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, asdict
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY,
    surface TEXT NOT NULL,            -- the shorthand form
    expansion TEXT NOT NULL,          -- current agreed full-fidelity meaning
    revision INTEGER NOT NULL DEFAULT 1,
    confidence REAL NOT NULL DEFAULT 0.5,
    proposed_by TEXT NOT NULL,
    ratified_by TEXT NOT NULL,        -- JSON list of node ids
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',  -- active | deprecated
    UNIQUE(surface, status)
);

CREATE TABLE IF NOT EXISTS revisions (
    id INTEGER PRIMARY KEY,
    entry_id INTEGER NOT NULL REFERENCES entries(id),
    revision INTEGER NOT NULL,
    prior_expansion TEXT NOT NULL,
    new_expansion TEXT NOT NULL,
    trigger TEXT NOT NULL,            -- 'ratification' | 'repair:<event_id>'
    ratified_by TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS escrow (
    id INTEGER PRIMARY KEY,
    message_id TEXT NOT NULL UNIQUE,
    sender TEXT NOT NULL,
    original TEXT NOT NULL,           -- full-fidelity source text
    compressed TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS repair_events (
    id INTEGER PRIMARY KEY,
    message_id TEXT NOT NULL,
    disagreeing_nodes TEXT NOT NULL,  -- JSON list
    decodings TEXT NOT NULL,          -- JSON map node_id -> decoded text
    resolution TEXT,                  -- filled when repair completes (phase 1+)
    tokens_at_event INTEGER NOT NULL, -- cumulative session tokens (for rate metric)
    created_at REAL NOT NULL
);
"""


@dataclass
class Entry:
    surface: str
    expansion: str
    revision: int
    confidence: float
    proposed_by: str
    ratified_by: list[str]
    entry_id: int | None = None


class Corpus:
    def __init__(self, path: str | Path = "data/corpus.db"):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # -- entries ------------------------------------------------------------
    def ratify(self, surface: str, expansion: str, proposed_by: str,
               ratified_by: list[str], confidence: float = 0.5) -> int:
        now = time.time()
        cur = self.conn.execute(
            "INSERT INTO entries (surface, expansion, confidence, proposed_by,"
            " ratified_by, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
            (surface, expansion, confidence, proposed_by,
             json.dumps(ratified_by), now, now))
        self.conn.commit()
        return cur.lastrowid

    def revise(self, entry_id: int, new_expansion: str, trigger: str,
               ratified_by: list[str]) -> int:
        row = self.conn.execute(
            "SELECT expansion, revision FROM entries WHERE id=?",
            (entry_id,)).fetchone()
        if row is None:
            raise KeyError(f"no entry {entry_id}")
        prior, rev = row
        now = time.time()
        self.conn.execute(
            "INSERT INTO revisions (entry_id, revision, prior_expansion,"
            " new_expansion, trigger, ratified_by, created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (entry_id, rev + 1, prior, new_expansion, trigger,
             json.dumps(ratified_by), now))
        self.conn.execute(
            "UPDATE entries SET expansion=?, revision=?, updated_at=? WHERE id=?",
            (new_expansion, rev + 1, now, entry_id))
        self.conn.commit()
        return rev + 1

    def active_entries(self) -> list[Entry]:
        rows = self.conn.execute(
            "SELECT id, surface, expansion, revision, confidence, proposed_by,"
            " ratified_by FROM entries WHERE status='active'").fetchall()
        return [Entry(entry_id=r[0], surface=r[1], expansion=r[2], revision=r[3],
                      confidence=r[4], proposed_by=r[5],
                      ratified_by=json.loads(r[6])) for r in rows]

    def as_prompt_block(self) -> str:
        """Render the ratified dictionary for injection into node system prompts."""
        entries = self.active_entries()
        if not entries:
            return "(corpus empty — no ratified entries yet)"
        return "\n".join(f"{e.surface} := {e.expansion}  [rev {e.revision},"
                         f" conf {e.confidence:.2f}]" for e in entries)

    # -- escrow -------------------------------------------------------------
    def escrow_put(self, message_id: str, sender: str, original: str,
                   compressed: str) -> None:
        self.conn.execute(
            "INSERT INTO escrow (message_id, sender, original, compressed,"
            " created_at) VALUES (?,?,?,?,?)",
            (message_id, sender, original, compressed, time.time()))
        self.conn.commit()

    def escrow_get(self, message_id: str) -> tuple[str, str] | None:
        row = self.conn.execute(
            "SELECT original, compressed FROM escrow WHERE message_id=?",
            (message_id,)).fetchone()
        return (row[0], row[1]) if row else None

    # -- repair -------------------------------------------------------------
    def log_repair_event(self, message_id: str, disagreeing_nodes: list[str],
                         decodings: dict[str, str], tokens_at_event: int) -> int:
        cur = self.conn.execute(
            "INSERT INTO repair_events (message_id, disagreeing_nodes,"
            " decodings, tokens_at_event, created_at) VALUES (?,?,?,?,?)",
            (message_id, json.dumps(disagreeing_nodes), json.dumps(decodings),
             tokens_at_event, time.time()))
        self.conn.commit()
        return cur.lastrowid

    def repair_events(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, message_id, disagreeing_nodes, decodings, resolution,"
            " tokens_at_event, created_at FROM repair_events ORDER BY id").fetchall()
        return [dict(id=r[0], message_id=r[1],
                     disagreeing_nodes=json.loads(r[2]),
                     decodings=json.loads(r[3]), resolution=r[4],
                     tokens_at_event=r[5], created_at=r[6]) for r in rows]
