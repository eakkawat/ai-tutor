from helpers import make_pdf

from ai_tutor.ingest.pdfinfo import read_pdf
from ai_tutor.pipeline.chunking import chunk_unit, ranges, units_from_bookmarks, units_from_windows


def test_chapters_from_bookmarks_keep_pages_and_never_cross(tmp_path):
    p = make_pdf(tmp_path / "b.pdf", [("Chapter 1: Want", 3), ("Chapter 2: Obstacle", 4), ("Chapter 3: Stakes", 2)])
    info = read_pdf(p)
    units = units_from_bookmarks(p, info.toc, info.pages)
    assert [(u.label, u.first, u.last) for u in units] == [("Ch. 1", 1, 3), ("Ch. 2", 4, 7), ("Ch. 3", 8, 9)]
    for u in units:
        pieces, missing = chunk_unit(u, max_chars=1500)
        assert pieces and missing == []
        assert pieces[0].pages[0] == u.first and pieces[-1].pages[1] == u.last
        assert all(u.first <= pc.pages[0] <= pc.pages[1] <= u.last for pc in pieces)


def test_no_bookmarks_falls_back_to_page_windows(tmp_path):
    p = make_pdf(tmp_path / "b.pdf", [("Chapter 1: Want", 12)], bookmarks=False)
    info = read_pdf(p)
    units = units_from_windows(p, info.pages, 1)
    assert [(u.first, u.last) for u in units] == [(1, 10), (11, 12)]


def test_pages_without_text_are_reported(tmp_path):
    p = make_pdf(tmp_path / "b.pdf", [("Chapter 1: Want", 5)], blank_pages=(3,))
    u = units_from_bookmarks(p, read_pdf(p).toc, 5)[0]
    pieces, missing = chunk_unit(u)
    assert missing == [3] and pieces


def test_ranges():
    assert ranges([3, 4, 5, 9]) == "3–5, 9"
