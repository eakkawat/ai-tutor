"""Read what the Inbox needs from a PDF: pages, metadata, bookmarks, whether it has text."""
# Copied from book-to-skills: book_to_skills/ingest/pdfinfo.py
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf as fitz  # PyMuPDF

# A page with fewer characters than this counts as empty (scans and blank pages).
MIN_TEXT_CHARS = 20


@dataclass
class PdfInfo:
    pages: int = 0
    title: str = ""
    author: str = ""
    toc: list[tuple[int, str, int]] = field(default_factory=list)   # (level, title, 1-based page)
    page_chars: list[int] = field(default_factory=list)             # characters on each page (first PROBE pages)
    first_text: str = ""
    error: str | None = None

    @property
    def has_text(self) -> bool:
        return any(c >= MIN_TEXT_CHARS for c in self.page_chars)

    @property
    def is_blank(self) -> bool:
        """No text and no images on any probed page: an empty separator file, not a scan."""
        return not self.has_text and self.pages > 0 and self.error is None and self._images == 0

    _images: int = 0


PROBE = 12   # pages looked at to decide "has a text layer"


def read_pdf(path: Path | str) -> PdfInfo:
    """Never raises: a damaged file comes back with `error` set so the Inbox can show it."""
    info = PdfInfo()
    try:
        with fitz.open(str(path)) as doc:
            info.pages = len(doc)
            md = doc.metadata or {}
            info.title = (md.get("title") or "").strip()
            info.author = (md.get("author") or "").strip()
            info.toc = [(lvl, (t or "").strip(), pg) for lvl, t, pg in doc.get_toc(simple=True)]
            for i in range(min(PROBE, len(doc))):
                page = doc[i]
                text = page.get_text("text") or ""
                info.page_chars.append(len(text.strip()))
                if i == 0:
                    info.first_text = text.strip()[:600]
                info._images += len(page.get_images())
    except Exception as e:  # noqa: BLE001 - PyMuPDF raises several unrelated types for bad files
        info.error = f"Cannot read this PDF: {e}"
    return info


def page_text(path: Path | str, page: int) -> str:
    """Text of one 1-based page."""
    with fitz.open(str(path)) as doc:
        return doc[page - 1].get_text("text") if 1 <= page <= len(doc) else ""
