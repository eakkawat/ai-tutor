"""Hybrid search (SPEC §7): keyword (FTS5) and embedding (sqlite-vec) results fused by reciprocal rank, linked sources first."""
import re
import sqlite3
from dataclasses import dataclass

import numpy as np

from .embeddings import Embedder, EmbeddingUnavailable

RRF_K = 60


@dataclass
class Hit:
    chunk_id: int
    source_id: int
    source_title: str
    label: str | None
    title: str | None
    page_start: int
    page_end: int
    text: str
    score: float


def fts_query(q: str) -> str | None:
    """Words only, OR-joined, so punctuation in a question never breaks the FTS syntax."""
    words = [w for w in re.findall(r"[A-Za-z0-9']+", q.lower()) if len(w) > 2]
    return " OR ".join(f'"{w}"' for w in dict.fromkeys(words)) or None


def keyword_ids(db: sqlite3.Connection, q: str, limit: int) -> list[int]:
    m = fts_query(q)
    if not m:
        return []
    return [r[0] for r in db.execute("SELECT rowid FROM chunk_fts WHERE chunk_fts MATCH ? ORDER BY bm25(chunk_fts) LIMIT ?", (m, limit))]


def vector_ids(db: sqlite3.Connection, embedder: Embedder, q: str, limit: int) -> list[int]:
    v = embedder.queries([q])[0].astype(np.float32)
    rows = db.execute("SELECT rowid FROM chunk_vec WHERE embedding MATCH ? AND k = ? ORDER BY distance", (v.tobytes(), limit))
    return [r[0] for r in rows]


def _fuse(*rankings: list[int]) -> dict[int, float]:
    score: dict[int, float] = {}
    for ranking in rankings:
        for rank, cid in enumerate(ranking):
            score[cid] = score.get(cid, 0.0) + 1.0 / (RRF_K + rank + 1)
    return score


def _load(db: sqlite3.Connection, scores: dict[int, float], k: int) -> list[Hit]:
    ids = sorted(scores, key=scores.get, reverse=True)[:k]
    hits = []
    for cid in ids:
        r = db.execute("SELECT c.*, s.title AS source_title FROM chunk c JOIN source s ON s.id = c.source_id WHERE c.id = ?", (cid,)).fetchone()
        if r:
            hits.append(Hit(r["id"], r["source_id"], r["source_title"], r["label"], r["title"], r["page_start"], r["page_end"], r["text"], scores[cid]))
    return hits


def search(db: sqlite3.Connection, embedder: Embedder | None, query: str, *, k: int = 8, prefer_sources: set[int] | None = None,
           pool: int = 60) -> list[Hit]:
    """Top `k` chunks. Chunks from `prefer_sources` (the skill's linked books) fill the list first; others only fill what is left.

    Without an embedder, or when it is unavailable, keyword results alone are used."""
    rankings = [keyword_ids(db, query, pool)]
    if embedder is not None:
        try:
            rankings.append(vector_ids(db, embedder, query, pool))
        except EmbeddingUnavailable:
            pass
    scores = _fuse(*rankings)
    if prefer_sources:
        marks = ",".join("?" * len(scores)) or "NULL"
        in_pref = {r[0] for r in db.execute(f"SELECT id FROM chunk WHERE id IN ({marks}) AND source_id IN ({','.join('?' * len(prefer_sources))})",
                                            [*scores, *prefer_sources])}
        first = _load(db, {c: s for c, s in scores.items() if c in in_pref}, k)
        if len(first) < k:
            first += _load(db, {c: s for c, s in scores.items() if c not in in_pref}, k - len(first))
        return first
    return _load(db, scores, k)
