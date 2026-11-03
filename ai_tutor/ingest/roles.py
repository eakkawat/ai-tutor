"""Guess what a file is (contents, preface, chapter 3, index...) from its name, then from its first page."""
# Copied from book-to-skills: book_to_skills/ingest/roles.py
import re
from dataclasses import dataclass

from .pdfinfo import PdfInfo

ROLES = ("toc", "preface", "introduction", "chapter", "appendix", "index", "bibliography", "other")
FRONT_MATTER = {"toc", "preface", "introduction"}
EXCLUDED_BY_DEFAULT = {"index", "bibliography"}

_WORDS = {w: i for i, w in enumerate(
    ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty"])}
_ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10,
          "xi": 11, "xii": 12, "xiii": 13, "xiv": 14, "xv": 15, "xvi": 16, "xvii": 17, "xviii": 18, "xix": 19, "xx": 20}

# (role, pattern) tried in order against the normalized title. First match wins.
_RULES = [
    ("toc", r"(table of )?contents?|toc|brief contents|detailed contents"),
    ("preface", r"preface|foreword|prologue|acknowledg\w*|about the (author|book)|praise"),
    ("introduction", r"introduction|intro|overview|how to use this book|read me first"),
    ("index", r"index|indices"),
    ("bibliography", r"bibliography|references|further reading|works cited|notes|endnotes|sources|glossary"),
    ("appendix", r"appendix|appendices|annex\w*"),
]
_CHAPTER = re.compile(r"^(?:chapter|ch|part|section|lesson)(?![a-z])[\s.:_-]*(\w+)?", re.IGNORECASE)
_LEADING_NUMBER = re.compile(r"^\s*(\d{1,3})\s*[_.\-\s]+(.*)$")
_PLAIN_NUMBER = re.compile(r"^\s*(\d{1,3})\s*[.\-:)]?\s+\S")


@dataclass
class Guess:
    role: str
    number: int | None = None
    include: bool = True
    front_matter: bool = False
    note: str | None = None


def split_filename(filename: str) -> tuple[int | None, str]:
    """`07_Chapter_One_The_What.pdf` -> (7, 'Chapter One The What'). The number is the file order."""
    stem = re.sub(r"\.pdf$", "", filename, flags=re.IGNORECASE)
    m = _LEADING_NUMBER.match(stem)
    order, rest = (int(m.group(1)), m.group(2)) if m else (None, stem)
    return order, re.sub(r"[_\s]+", " ", rest).strip()


def _number(token: str | None) -> int | None:
    if not token:
        return None
    t = token.lower().strip(".:")
    if t.isdigit():
        return int(t)
    return _WORDS.get(t) or _ROMAN.get(t)


# Longest title (in words) that still counts as that section. "Introduction to Story Design" is a chapter;
# "Introduction" is the introduction.
_MAX_WORDS = {"toc": 3, "preface": 3, "introduction": 2, "index": 3, "bibliography": 3, "appendix": 8}


def classify_title(title: str) -> tuple[str, int | None] | None:
    t = title.strip().lower()
    if not t:
        return None
    for role, pat in _RULES:
        if re.match(rf"(?:{pat})\b", t) and len(t.split()) <= _MAX_WORDS[role]:
            return role, None
    m = _CHAPTER.match(t)
    if m:
        return "chapter", _number(m.group(1))
    return None


def detect_role(filename: str, info: PdfInfo | None = None) -> Guess:
    """Name first (the splitter writes the chapter title into the filename), first page text as a fallback."""
    _, title = split_filename(filename)
    hit = classify_title(title)
    if hit is None and info is not None and info.first_text:
        first_line = next((ln for ln in info.first_text.splitlines() if ln.strip()), "")
        hit = classify_title(first_line)
    if hit is None:
        # A numbered title with real words after it is almost always a chapter ("03 The Midpoint").
        role, number = ("chapter", None) if re.search(r"[A-Za-z]{3,}", title) else ("other", None)
        hit = (role, number)
    role, number = hit
    if role == "chapter" and number is None:
        m = _PLAIN_NUMBER.match(title)
        number = int(m.group(1)) if m else None
    g = Guess(role=role, number=number, include=role not in EXCLUDED_BY_DEFAULT, front_matter=role in FRONT_MATTER)
    if info is not None:
        if info.error:
            g.include, g.note = False, "unreadable"
        elif info.is_blank:
            g.role, g.include, g.note = "other", False, "blank"
        elif not info.has_text:
            g.include, g.note = False, "needs_ocr"
    return g
