"""Split a book by its own structure (chapters, then sections), never by token count. Every chunk keeps its pages.

Adapted from book-to-skills `pipeline/chunking.py`: the unit finding, page reading and page grouping are copied; storing chunks in SQLite
and the retrieval-sized limit are new.
"""
import re
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from ..ingest.roles import classify_title

MIN_CHUNK_CHARS = 200            # a divider page or an empty scan is not worth indexing
MAX_CHUNK_CHARS = 2500           # retrieval-sized: about 600 tokens
WINDOW_PAGES = 10                # fallback when a whole-book PDF has no usable bookmarks
JUNK_TITLES = re.compile(r"^(title page|half title|cover|back cover|front cover|copyright|dedication|also by|about the (author|authors|book)|"
                         r"praise|endorsements|colophon|table of contents|contents|index|bibliography|references|acknowledg\w*|foreword.*|preface.*)$", re.IGNORECASE)
_CHAPTER_NUM = re.compile(r"^(?:chapter|ch\.?)\s+(\w+)", re.IGNORECASE)
SKIP_ROLES = {"toc", "index", "bibliography", "preface"}


@dataclass
class Unit:
    """One chapter or section of the book, before it is cut into chunks."""
    source: Path
    title: str
    chapter: int | None
    first: int
    last: int
    boundaries: tuple[int, ...] = ()       # pages where a sub-section starts: preferred cut points when the unit is too long
    file_id: int | None = None

    @property
    def label(self) -> str:
        return f"Ch. {self.chapter}" if self.chapter else self.title


def _number(title: str) -> int | None:
    from ..ingest.roles import _number
    m = _CHAPTER_NUM.match(title.strip())
    return _number(m.group(1)) if m else None


def units_from_bookmarks(path: Path, toc: list[tuple[int, str, int]], pages: int) -> list[Unit]:
    """Leaf bookmarks are the chapters. Front and back matter is dropped by name. A chapter that has sub-sections keeps its lead-in."""
    units: list[Unit] = []
    for i, (level, title, page) in enumerate(toc):
        nxt = toc[i + 1] if i + 1 < len(toc) else None
        is_leaf = nxt is None or nxt[0] <= level
        end = (max(page, nxt[2] - 1) if nxt and nxt[2] > page else page) if nxt else pages
        # A Part or section heading is only a divider. A *chapter* that has sub-sections keeps its own lead-in pages
        # (from its page to its first sub-section's page), if it has any.
        if not is_leaf and (_number(title) is None or nxt[2] <= page):
            continue
        if re.match(r"^part\s+\w+\b", title.strip(), re.IGNORECASE):
            continue
        if JUNK_TITLES.match(title.strip()) or (classify_title(title) or ("", 0))[0] in SKIP_ROLES:
            continue
        subs = tuple(p for lvl, _t, p in toc[i + 1:] if lvl > level and p <= end) if not is_leaf else ()
        units.append(Unit(path, title.strip(), _number(title), max(page, 1), min(end, pages), subs))
    return units


def units_from_windows(path: Path, pages: int, start: int) -> list[Unit]:
    return [Unit(path, f"Pages {a}–{min(a + WINDOW_PAGES - 1, pages)}", None, a, min(a + WINDOW_PAGES - 1, pages))
            for a in range(max(start, 1), pages + 1, WINDOW_PAGES)]


def page_texts(path: Path, first: int, last: int) -> list[tuple[int, str]]:
    out = []
    with pymupdf.open(str(path)) as doc:
        for n in range(first, last + 1):
            if 1 <= n <= len(doc):
                t = re.sub(r"[ \t]+", " ", doc[n - 1].get_text("text") or "").strip()
                if t:
                    out.append((n, t))
    return out


def cut(pages: list[tuple[int, str]], max_chars: int, boundaries: tuple[int, ...] = ()) -> list[list[tuple[int, str]]]:
    """Group pages into chunks of at most `max_chars`. Cut at a sub-section start when one is near, else between pages;
    a single page longer than the limit is split at paragraph breaks (the last resort)."""
    groups: list[list[tuple[int, str]]] = []
    cur: list[tuple[int, str]] = []
    size = 0
    for n, text in pages:
        if len(text) > max_chars:                                       # one huge page: paragraph fallback
            if cur:
                groups.append(cur)
                cur, size = [], 0
            groups.extend([(n, part)] for part in _split_paragraphs(text, max_chars))
            continue
        if cur and size + len(text) > max_chars:
            at = next((i for i in range(len(cur) - 1, 0, -1) if cur[i][0] in boundaries and sum(len(t) for _, t in cur[:i]) >= max_chars // 3), None)
            if at is not None:
                groups.append(cur[:at])
                cur = cur[at:]
            else:
                groups.append(cur)
                cur = []
            size = sum(len(t) for _, t in cur)
        cur.append((n, text))
        size += len(text)
    if cur:
        groups.append(cur)
    # a short tail (two pages after a long chapter) costs a whole model call for little text: fold it into the chunk before it
    if len(groups) > 1 and _chars(groups[-1]) < max_chars // 4 and _chars(groups[-2]) + _chars(groups[-1]) <= max_chars * 1.3 and len(groups[-1]) < 4:
        tail = groups.pop()
        groups[-1] = groups[-1] + tail
    return groups


def _chars(group: list[tuple[int, str]]) -> int:
    return sum(len(t) for _, t in group)


def _split_paragraphs(text: str, max_chars: int) -> list[str]:
    parts, cur = [], ""
    for para in re.split(r"\n\s*\n|\n", text):
        while len(para) > max_chars:                                    # a paragraph with no breaks at all
            parts.append(para[:max_chars])
            para = para[max_chars:]
        if cur and len(cur) + len(para) + 1 > max_chars:
            parts.append(cur)
            cur = ""
        cur = f"{cur}\n{para}" if cur else para
    if cur:
        parts.append(cur)
    return parts


@dataclass
class Piece:
    title: str
    label: str
    pages: tuple[int, int]
    text: str


def chunk_unit(u: Unit, max_chars: int = MAX_CHUNK_CHARS) -> tuple[list[Piece], list[int]]:
    """Cut one unit into pieces. Also returns the pages in the unit that have no text (scanned or blank), so the caller can flag them."""
    pages = page_texts(u.source, u.first, u.last)
    have = {n for n, _ in pages}
    missing = [n for n in range(u.first, u.last + 1) if n not in have]
    if sum(len(t) for _, t in pages) < MIN_CHUNK_CHARS:
        return [], missing
    out: list[Piece] = []
    for group in cut(pages, max_chars, u.boundaries):
        text = "\n\n".join(t for _, t in group)
        if len(text) < MIN_CHUNK_CHARS and out:
            continue
        out.append(Piece(u.title, u.label, (group[0][0], group[-1][0]), text))
    return out, missing


def ranges(pages: list[int]) -> str:
    """[3, 4, 5, 9] -> '3-5, 9'"""
    out, i = [], 0
    while i < len(pages):
        j = i
        while j + 1 < len(pages) and pages[j + 1] == pages[j] + 1:
            j += 1
        out.append(str(pages[i]) if i == j else f"{pages[i]}\u2013{pages[j]}")
        i = j + 1
    return ", ".join(out)
