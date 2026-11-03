"""Single whole-book PDF: where are the contents, preface and introduction? Bookmarks first, then page text."""
# Copied from book-to-skills: book_to_skills/ingest/front_matter.py
from pathlib import Path

import pymupdf as fitz

from .pdfinfo import PdfInfo
from .roles import FRONT_MATTER, classify_title

SCAN_PAGES = 40        # front matter lives near the start
MAX_SECTION_PAGES = 15  # a text-scanned section never claims more than this


def _from_bookmarks(info: PdfInfo) -> dict[str, list[int]]:
    found: dict[str, list[int]] = {}
    toc = info.toc
    for i, (level, title, page) in enumerate(toc):
        hit = classify_title(title)
        if not hit or hit[0] not in FRONT_MATTER or hit[0] in found or page < 1:
            continue
        end = page
        for lvl2, _t2, p2 in toc[i + 1:]:
            if lvl2 <= level:
                end = max(page, p2 - 1) if p2 > page else page
                break
        else:
            end = min(info.pages, page + MAX_SECTION_PAGES - 1)
        found[hit[0]] = [page, end]
    return found


def _heading(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return ""


def _from_text(path: Path | str, pages: int) -> dict[str, list[int]]:
    found: dict[str, list[int]] = {}
    current: tuple[str, int] | None = None
    with fitz.open(str(path)) as doc:
        for n in range(min(pages, SCAN_PAGES)):
            hit = classify_title(_heading(doc[n].get_text("text") or ""))
            role = hit[0] if hit else None
            runs_on = current and n + 1 - current[1] < MAX_SECTION_PAGES
            if role in FRONT_MATTER and role not in found:
                if current:
                    found[current[0]][1] = n
                current = (role, n + 1)
                found[role] = [n + 1, n + 1]
            elif role is not None and current:     # a different section starts: close the open one
                found[current[0]][1] = n
                current = None
            elif current and runs_on:              # still inside the section (e.g. contents on page 2 of 3)
                found[current[0]][1] = n + 1
    return found


def find_front_matter(path: Path | str, info: PdfInfo) -> dict[str, list[int]]:
    """{'toc': [5, 7], 'introduction': [9, 14]}: 1-based inclusive page ranges. Empty if nothing is found."""
    if info.error or not info.pages:
        return {}
    found = _from_bookmarks(info)
    if set(found) >= {"toc"} or len(found) >= 2:
        return found
    if info.has_text:
        for role, rng in _from_text(path, info.pages).items():
            found.setdefault(role, rng)
    return found
