"""Citations (SPEC §7): `[Book title, ch. X, p. Y]`. Every citation must point to a chunk that was actually retrieved.

`validate` checks generated text against the retrieved chunks, strips or flags the ones that do not match, and returns which chunk each
valid citation opens. No invented quotes, page numbers or book content survive.
"""
import re
from dataclasses import dataclass, field

from .search import Hit

# [Book A, ch. 3, p. 41]   [Book A, p. 41]   [Book A, ch. 3, pp. 41–43]
CITATION = re.compile(r"\[([^\[\]]+?),\s*(?:ch\.\s*([^,\]]+?),\s*)?pp?\.\s*(\d+)(?:\s*[–-]\s*(\d+))?\s*\]")
OUTSIDE = "[outside my books]"


def cite(hit_or_row) -> str:
    """The citation string for a chunk (a `Hit`, or a dict with the same fields)."""
    g = (lambda k: getattr(hit_or_row, k)) if hasattr(hit_or_row, "source_title") else (lambda k: hit_or_row[k])
    label = g("label") or ""
    ch = ""
    if label.lower().startswith("ch."):
        ch = f", ch. {label[3:].strip()}"
    elif label and not label.lower().startswith("pages "):      # page-window units have no chapter to name
        ch = f", ch. {label}"
    a, b = g("page_start"), g("page_end")
    return f"[{g('source_title')}{ch}, {'p. ' + str(a) if a == b else f'pp. {a}–{b}'}]"


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _chapter_ok(hit: Hit, ch: str | None) -> bool:
    if ch is None:
        return True
    want = _norm(ch)
    label = _norm(hit.label or "")
    return want in {label, _norm(label.removeprefix("ch ")), _norm(hit.title or "")}


def resolve(book: str, ch: str | None, p1: int, p2: int | None, chunks: list[Hit]) -> Hit | None:
    lo, hi = p1, p2 or p1
    for h in chunks:
        if _norm(h.source_title) != _norm(book) or not _chapter_ok(h, ch):
            continue
        if h.page_start <= lo and hi <= h.page_end:
            return h
    return None


@dataclass
class Checked:
    text: str
    valid: list[dict] = field(default_factory=list)       # [{"citation": str, "chunk_id": int}]
    invalid: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.valid) and not self.invalid


def validate(text: str, chunks: list[Hit], *, mode: str = "strip") -> Checked:
    """`mode="strip"` removes citations that match no retrieved chunk; `"flag"` replaces them with `[citation not found]`."""
    out = Checked(text)
    seen: set[int] = set()

    def sub(m: re.Match) -> str:
        book, ch, p1, p2 = m.group(1), m.group(2), int(m.group(3)), int(m.group(4)) if m.group(4) else None
        hit = resolve(book, ch, p1, p2, chunks)
        if hit is None:
            out.invalid.append(m.group(0))
            return "" if mode == "strip" else "[citation not found]"
        if hit.chunk_id not in seen:
            seen.add(hit.chunk_id)
            out.valid.append({"citation": m.group(0), "chunk_id": hit.chunk_id})
        return m.group(0)

    out.text = re.sub(r"[ \t]+([.,;:])", r"\1", CITATION.sub(sub, text)) if mode == "strip" else CITATION.sub(sub, text)
    return out
