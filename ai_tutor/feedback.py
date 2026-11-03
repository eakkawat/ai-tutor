"""Principle-based feedback (SPEC §6.1.1): the work is judged only against the skill's checklist, item by item.

Every principle gets followed / partly / not followed. A "followed" or "partly" verdict needs evidence: an exact quote from the work,
which the code finds and turns into a line number (the model's own line numbers are never trusted). A "followed" with no findable
evidence is downgraded to "partly". Pass = every principle followed. Each fix is tied to a principle and carries its book citation.
"""
import bisect
import difflib
import json
import re
import sqlite3
from datetime import datetime

from pydantic import BaseModel, Field

from . import media
from .assets import Bundle
from .citations import CITATION
from .llm.prompts import fence
from .teaching import Ctx, TutorError, _ask, concepts_text, count_words, diagnosis_text, trim_words

MIN_SUBMISSION_CHARS = 15
MIN_SUBMISSION_WORDS = 3
MAX_FIXES = 2
RANK = {"not": 0, "partly": 1, "followed": 2}
WORDS = {"followed": "Followed", "partly": "Partly", "not": "Not followed"}


class FbPrinciple(BaseModel):
    n: int
    result: str
    quote: str = ""
    comment: str = ""
    kind: str = "line"                     # line (text) | image | video
    asset: int | None = None               # the IMAGE or VIDEO number in the prompt
    region: list[float] | None = None      # image: [x, y, width, height] as fractions of the picture
    start_s: float | None = None           # video: where it happens, in seconds
    end_s: float | None = None


class FbFix(BaseModel):
    n: int
    fix: str
    example: str = ""


class FbMistake(BaseModel):
    n: int
    kind: str
    concept: str | None = None
    tag: str = ""


class FeedbackOut(BaseModel):
    principles: list[FbPrinciple] = Field(default_factory=list)
    fixes: list[FbFix] = Field(default_factory=list)
    mistakes: list[FbMistake] = Field(default_factory=list)
    concepts_shown: list[str] = Field(default_factory=list)
    since_last: str = ""
    summary: str = ""


def too_short(text: str) -> bool:
    return len(text.strip()) < MIN_SUBMISSION_CHARS or count_words(text) < MIN_SUBMISSION_WORDS


def numbered(text: str) -> str:
    return "\n".join(f"{i}: {line}" for i, line in enumerate(text.splitlines() or [""], 1))


def _squash(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower()).strip()


def locate(quote: str, work: str) -> tuple[int, int] | None:
    """Lines (1-based, inclusive) of the work that hold `quote`, ignoring case and spacing. None when it is not in the work."""
    q = _squash(quote)
    if not q:
        return None
    flat, starts, pos = "", [], 0
    for line in work.splitlines() or [""]:
        starts.append(pos)
        piece = _squash(line)
        flat += piece + " "
        pos += len(piece) + 1
    i = flat.find(q)
    if i < 0:
        return None
    a = bisect.bisect_right(starts, i) - 1
    b = bisect.bisect_right(starts, i + len(q) - 1) - 1
    return a + 1, b + 1


def locator_text(span: tuple[int, int] | None) -> str | None:
    if span is None:
        return None
    return f"Line {span[0]}" if span[0] == span[1] else f"Lines {span[0]}–{span[1]}"


def _plain(s: str) -> str:
    """Model prose with any bracketed citation removed: the citation shown beside a verdict is attached by code, from the skill's own principle."""
    return re.sub(r"\s{2,}", " ", re.sub(r"\s+([.,;:])", r"\1", CITATION.sub("", s))).strip()


def _short(s: str, n: int) -> str:
    return trim_words(_plain(s), n)


def previous_text(db: sqlite3.Connection, session_id: int, before_version: int) -> tuple[str, dict[int, str]]:
    """The last feedback's summary line and its verdict per principle number (empty on the first attempt)."""
    row = db.execute("SELECT f.id, f.content FROM feedback f JOIN submission su ON su.id = f.submission_id "
                     "WHERE su.session_id = ? AND su.version < ? ORDER BY su.version DESC LIMIT 1", (session_id, before_version)).fetchone()
    if row is None:
        return "", {}
    checks = db.execute("SELECT sp.\"order\" AS ord, pc.result, pc.comment FROM principle_check pc JOIN skill_principle sp ON sp.id = pc.principle_id "
                        "WHERE pc.feedback_id = ? ORDER BY sp.\"order\", sp.id", (row["id"],)).fetchall()
    verdicts = {i: c["result"] for i, c in enumerate(checks, 1)}
    text = row["content"] + "\n" + "\n".join(f"{i}. {WORDS[c['result']]}: {c['comment']}" for i, c in enumerate(checks, 1))
    return text, verdicts


def revision_diff(old: str, new: str, before: dict[int, str], after: dict[int, str]) -> dict:
    """What changed between two attempts, worked out in code: per principle, and in lines of the work."""
    sm = difflib.SequenceMatcher(None, old.splitlines(), new.splitlines())
    added = removed = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("replace", "delete"):
            removed += i2 - i1
        if tag in ("replace", "insert"):
            added += j2 - j1
    ps = []
    for n, a in sorted(after.items()):
        b = before.get(n)
        change = "same" if b is None or RANK[a] == RANK[b] else ("improved" if RANK[a] > RANK[b] else "worse")
        ps.append({"n": n, "before": b, "after": a, "change": change})
    return {"principles": ps, "lines_added": added, "lines_removed": removed}


def diff_sentence(d: dict) -> str:
    better = [p["n"] for p in d["principles"] if p["change"] == "improved"]
    worse = [p["n"] for p in d["principles"] if p["change"] == "worse"]
    parts = []
    if better:
        parts.append("Improved: principle" + ("s " if len(better) > 1 else " ") + ", ".join(map(str, better)))
    if worse:
        parts.append("Got worse: principle" + ("s " if len(worse) > 1 else " ") + ", ".join(map(str, worse)))
    return ". ".join(parts) + "." if parts else "No principle changed its verdict."


def line_diff(old: str, new: str) -> list[dict]:
    """For the 'Compare attempts' view: every line of the new work marked as kept, added, or (from the old work) removed."""
    out = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, old.splitlines(), new.splitlines()).get_opcodes():
        if tag == "equal":
            out += [{"op": " ", "text": t} for t in new.splitlines()[j1:j2]]
        else:
            out += [{"op": "-", "text": t} for t in old.splitlines()[i1:i2]] + [{"op": "+", "text": t} for t in new.splitlines()[j1:j2]]
    return out


def generate(ctx: Ctx, *, task: dict | None, work: str, attempt: int, previous: str, bundle: Bundle | None = None) -> dict:
    """Ask for feedback and check it. Raises TutorError (nothing stored) if the verdicts are incomplete after one more try."""
    skill = ctx.skill
    bundle = bundle or Bundle()
    if not bundle.empty() and ctx.vision is False:
        raise TutorError("The language model you set up cannot read pictures, so I cannot judge the pictures or clips in this attempt. "
                         "Switch to a model that can read images in Setup, or remove them and submit the text.", retryable=False)
    n_total = len(skill["principles"])
    principles = "\n".join(f"{i}. {p['principle']} (test: {p['test']}) {p['citation'] or ''}" for i, p in enumerate(skill["principles"], 1))
    values = {"attempt": str(attempt), "task": fence("task", (task or {}).get("instructions", "(none)")),
              "work": fence("learner work", numbered(work) if work.strip() else "(no text: the work is in the pictures or clips)"),
              "attachments": fence("attachments", bundle.prompt_text()),
              "concepts": concepts_text(ctx.db, skill["id"]), "previous": fence("previous feedback", previous or "(none: this is the first attempt)"),
              "diagnosis": fence("diagnosis", diagnosis_text(ctx.db, ctx.session_id))}
    note = ""
    for _ in (1, 2):
        out = _ask(ctx, FeedbackOut, "feedback", "feedback", images=bundle.data_urls() or None, principles=principles + note, **values)
        seen = [p.n for p in out.principles]
        if sorted(seen) == list(range(1, n_total + 1)):
            return _check(ctx, out, work, bundle)
        missing = sorted(set(range(1, n_total + 1)) - set(seen))
        note = (f"\n\nYour last reply did not give exactly one verdict for every numbered principle (missing: {missing or 'none'}; "
                "repeated or unknown numbers are not allowed).")
    raise TutorError("The feedback came back incomplete: not every principle got a verdict. Nothing was saved; try again.")


def _position(region: list[float]) -> str:
    """'upper left', 'centre', 'lower right'... from the middle of the region, so a locator can name the part of the picture."""
    cx, cy = region[0] + region[2] / 2, region[1] + region[3] / 2
    v = "upper" if cy < 0.34 else "lower" if cy > 0.66 else ""
    h = "left" if cx < 0.34 else "right" if cx > 0.66 else ""
    return " ".join(x for x in (v, h) if x) or "centre"


def _num(x) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def media_evidence(v: FbPrinciple, bundle: Bundle) -> dict | None:
    """Evidence that points into a picture or a clip, checked against what was actually attached. None if it points at nothing real."""
    if v.kind == "image":
        img = bundle.image(v.asset)
        if img is None:
            return None
        region = None
        if v.region and len(v.region) == 4 and all(_num(x) is not None for x in v.region):
            x, y, w, h = (float(t) for t in v.region)
            if 0 <= x < 1 and 0 <= y < 1 and w > 0 and h > 0:
                region = [round(x, 3), round(y, 3), round(min(w, 1 - x), 3), round(min(h, 1 - y), 3)]
        where = f"Image {img['n']}" + (f", {_position(region)}" if region else "")
        return {"kind": "image", "n": img["n"], "asset_id": img["asset_id"], "filename": img["filename"], "region": region, "locator": where}
    if v.kind == "video":
        vid = bundle.video(v.asset)
        a, b = _num(v.start_s), _num(v.end_s if v.end_s is not None else v.start_s)
        if vid is None or a is None or b is None or not vid["frames"]:
            return None
        a, b = max(0.0, min(a, b)), min(float(vid["duration"]), max(a, b))
        if a > vid["duration"]:
            return None
        inside = [f for f in vid["frames"] if a - 1.0 <= f["t"] <= b + 1.0] or [min(vid["frames"], key=lambda f: abs(f["t"] - (a + b) / 2))]
        return {"kind": "video", "n": vid["n"], "asset_id": vid["asset_id"], "filename": vid["filename"], "start_s": a, "end_s": b,
                "frames": [{"id": f["id"], "idx": f["idx"], "t": f["t"]} for f in inside[:4]], "locator": f"Video {vid['n']} · {media.fmt_range(a, b)}"}
    return None


def _check(ctx: Ctx, out: FeedbackOut, work: str, bundle: Bundle) -> dict:
    skill = ctx.skill
    by_n = {p.n: p for p in out.principles}
    results = []
    for i, pr in enumerate(skill["principles"], 1):
        v = by_n[i]
        result = v.result.strip().lower().replace("not followed", "not").replace("partially", "partly")
        result = result if result in RANK else "not"
        kind = v.kind.strip().lower()
        ev = media_evidence(v, bundle) if kind in ("image", "video") else None
        span = locate(v.quote, work) if (ev is None and v.quote.strip()) else None
        comment = _short(v.comment, 40)
        if result == "followed" and span is None and ev is None:          # no findable evidence: it cannot count as followed
            result, comment = "partly", "I could not find the evidence for this in your work, so it does not count as followed yet."
        results.append({"n": i, "principle_id": pr["id"], "principle": pr["principle"], "test": pr["test"], "result": result, "comment": comment,
                        "quote": v.quote.strip() if span else "", "locator": ev["locator"] if ev else locator_text(span), "span": list(span) if span else None,
                        "evidence": ev, "citation": pr["citation"], "chunk_id": pr["chunk_id"]})
    failing = [r["n"] for r in results if r["result"] != "followed"]
    passed = not failing
    fixes = []
    for f in out.fixes:
        if f.n in failing and len(fixes) < MAX_FIXES and f.n not in {x["n"] for x in fixes}:
            r = results[f.n - 1]
            fixes.append({"n": f.n, "fix": _short(f.fix, 30), "example": _short(f.example, 25), "citation": r["citation"], "chunk_id": r["chunk_id"],
                          "principle": r["principle"]})
    for n in failing:                                        # never leave a failing principle without a fix
        if len(fixes) >= MAX_FIXES:
            break
        if n not in {x["n"] for x in fixes}:
            r = results[n - 1]
            fixes.append({"n": n, "fix": f"Make this true of your work: {r['principle']}", "example": "", "citation": r["citation"], "chunk_id": r["chunk_id"],
                          "principle": r["principle"]})
    concept_ids = {c["name"].lower(): c["id"] for c in skill["concepts"]}
    mistakes, covered = [], set()
    for m in out.mistakes:
        if m.n not in failing or m.n in covered:
            continue
        kind = m.kind.strip().lower()
        cid = concept_ids.get((m.concept or "").strip().lower())
        if kind == "concept" and cid is None:
            kind = "execution"                                # a concept mistake must name a concept of this skill, or it cannot be re-taught
        mistakes.append({"n": m.n, "kind": kind if kind in ("concept", "execution") else "execution", "concept_id": cid if kind == "concept" else None,
                         "concept": m.concept if kind == "concept" else None, "tag": _short(m.tag, 4) or "unclear mistake"})
        covered.add(m.n)
    for n in failing:
        if n not in covered:
            mistakes.append({"n": n, "kind": "execution", "concept_id": None, "concept": None, "tag": _short(results[n - 1]["principle"], 4)})
    shown = [concept_ids[c.strip().lower()] for c in out.concepts_shown if c.strip().lower() in concept_ids]
    summary = ("Passed: every principle is followed." if passed
               else f"Not passed yet: {len(results) - len(failing)} of {len(results)} principles followed.")
    return {"results": results, "fixes": fixes, "mistakes": mistakes, "concepts_shown": shown, "passed": passed, "summary": summary,
            "since_last": _short(out.since_last, 30)}


def save(db: sqlite3.Connection, submission_id: int, skill_id: int, fb: dict, now: datetime) -> int:
    """Store the verdicts and the mistakes. A mistake seen again adds to its count (the frustration barrier reads it in TASKS_008)."""
    fid = db.execute("INSERT INTO feedback(submission_id, content, mistakes_json, passed) VALUES (?,?,?,?)",
                     (submission_id, fb["summary"], json.dumps(fb["mistakes"]), int(fb["passed"]))).lastrowid
    for r in fb["results"]:
        ev = r.get("evidence") or ({"kind": "line", "quote": r["quote"], "start": r["span"][0], "end": r["span"][1]} if r["span"] else None)
        db.execute("INSERT INTO principle_check(feedback_id, principle_id, result, evidence_ref, comment, locator) VALUES (?,?,?,?,?,?)",
                   (fid, r["principle_id"], r["result"], json.dumps(ev) if ev else None, r["comment"], r["locator"]))
    stamp = now.strftime("%Y-%m-%d %H:%M:%S")
    for m in fb["mistakes"]:
        chunk = fb["results"][m["n"] - 1]["chunk_id"]
        row = db.execute("SELECT id, count FROM mistake WHERE skill_id = ? AND kind = ? AND lower(tag) = lower(?)", (skill_id, m["kind"], m["tag"])).fetchone()
        if row:
            db.execute("UPDATE mistake SET count = count + 1, last_seen_at = ?, concept_id = COALESCE(?, concept_id) WHERE id = ?", (stamp, m["concept_id"], row["id"]))
            m["count"] = row["count"] + 1
        else:
            db.execute("INSERT INTO mistake(skill_id, concept_id, kind, tag, principle_chunk_id, count, last_seen_at) VALUES (?,?,?,?,?,1,?)",
                       (skill_id, m["concept_id"], m["kind"], m["tag"], chunk, stamp))
            m["count"] = 1
    db.execute("UPDATE feedback SET mistakes_json = ? WHERE id = ?", (json.dumps(fb["mistakes"]), fid))
    db.commit()
    return fid
