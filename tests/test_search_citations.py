import sqlite3

import numpy as np
from helpers import FakeEmbedder

from ai_tutor.citations import cite, validate
from ai_tutor.pipeline.chunking import MAX_CHUNK_CHARS  # noqa: F401
from ai_tutor.search import Hit, fts_query, search
from ai_tutor.store.conn import open_db


def seed(db: sqlite3.Connection, emb: FakeEmbedder):
    db.execute("INSERT INTO source(id, title) VALUES (1, '[Book A]'), (2, '[Book B]')")
    rows = [
        (1, 1, "Ch. 3", 41, 43, "A scene needs a character who wants something and an obstacle in the way."),
        (2, 1, "Ch. 4", 60, 61, "Subtext is what a character means but does not say aloud."),
        (3, 2, "Ch. 1", 10, 11, "A scene needs a want. Without a want the scene has no obstacle either."),
        (4, 2, "Ch. 2", 20, 22, "The invoice must be paid within thirty days of delivery."),
    ]
    for cid, sid, label, a, b, text in rows:
        db.execute("INSERT INTO chunk(id, source_id, label, title, chapter, page_start, page_end, text) VALUES (?,?,?,?,?,?,?,?)",
                   (cid, sid, label, label, label, a, b, text))
        db.execute("INSERT INTO chunk_vec(rowid, embedding) VALUES (?, ?)", (cid, emb.documents([text])[0].astype(np.float32).tobytes()))
    db.commit()


def db_with_chunks(tmp_path):
    db, emb = open_db(tmp_path / "a.db"), FakeEmbedder()
    seed(db, emb)
    return db, emb


def test_fts_query_is_safe_for_punctuation():
    assert fts_query('What is "subtext"? (and AND)') == '"what" OR "subtext" OR "and"'
    assert fts_query("?!") is None


def test_hybrid_finds_relevant_chunk_first(tmp_path):
    db, emb = db_with_chunks(tmp_path)
    hits = search(db, emb, "what does subtext mean", k=3)
    assert hits[0].chunk_id == 2
    assert not any(h.chunk_id == 4 for h in hits[:2])


def test_linked_sources_come_first(tmp_path):
    db, emb = db_with_chunks(tmp_path)
    plain = search(db, emb, "scene want obstacle", k=3)
    assert {h.chunk_id for h in plain[:2]} == {1, 3}
    pref = search(db, emb, "scene want obstacle", k=3, prefer_sources={2})
    assert pref[0].source_id == 2 and pref[0].chunk_id == 3
    assert any(h.source_id == 1 for h in pref)               # others only fill what is left


def test_keyword_only_when_no_embedder(tmp_path):
    db, _ = db_with_chunks(tmp_path)
    assert search(db, None, "invoice thirty days", k=2)[0].chunk_id == 4


def test_cite_format():
    h = Hit(1, 1, "[Book A]", "Ch. 3", "t", 41, 41, "x", 1.0)
    assert cite(h) == "[[Book A], ch. 3, p. 41]"
    h2 = Hit(1, 1, "Book A", "Ch. 3", "t", 41, 43, "x", 1.0)
    assert cite(h2) == "[Book A, ch. 3, pp. 41–43]"
    assert cite({"source_title": "Book A", "label": "Pages 1–10", "page_start": 5, "page_end": 5}) == "[Book A, p. 5]"
    assert cite({"source_title": "Book A", "label": "Story", "page_start": 5, "page_end": 5}) == "[Book A, ch. Story, p. 5]"


CHUNKS = [Hit(1, 1, "Book A", "Ch. 3", "Want", 41, 43, "x", 1.0), Hit(2, 2, "Book B", "Ch. 1", "Start", 10, 11, "y", 1.0)]


def test_valid_citations_resolve_to_chunks():
    r = validate("A want drives a scene [Book A, ch. 3, p. 42]. See also [Book B, ch. 1, pp. 10–11].", CHUNKS)
    assert [v["chunk_id"] for v in r.valid] == [1, 2] and r.invalid == [] and r.ok


def test_invented_citations_are_stripped():
    r = validate("Claim [Book A, ch. 3, p. 99]. Another [Book Z, p. 1]. Fine [Book A, p. 41].", CHUNKS)
    assert len(r.invalid) == 2
    assert "p. 99" not in r.text and "Book Z" not in r.text and "[Book A, p. 41]" in r.text
    assert "  " not in r.text and " ." not in r.text
    assert not r.ok


def test_wrong_chapter_for_a_real_page_is_invalid():
    assert validate("[Book A, ch. 9, p. 42]", CHUNKS).invalid == ["[Book A, ch. 9, p. 42]"]


def test_flag_mode_marks_instead_of_removing():
    r = validate("Claim [Book A, ch. 3, p. 99].", CHUNKS, mode="flag")
    assert "[citation not found]" in r.text


def test_no_citation_at_all_is_not_ok():
    r = validate("A claim with no source.", CHUNKS)
    assert not r.ok and r.valid == []
