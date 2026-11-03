"""Fixtures for the library tests: tiny made-up PDFs ([Book A]), a deterministic embedder, and a scripted language model."""
import hashlib
import re
from pathlib import Path

import numpy as np
import pymupdf

from ai_tutor.embeddings import DIM
from ai_tutor.llm.backends import Completion

LOREM = ("A scene needs a character who wants something and an obstacle in the way. {topic} The reader should feel the pressure rise "
         "as each attempt fails. ") * 6


def make_pdf(path: Path, chapters: list[tuple[str, int]], *, bookmarks: bool = True, title: str = "[Book A]", author: str = "[Author]",
             blank_pages: tuple[int, ...] = ()) -> Path:
    """One PDF. `chapters` = [(chapter title, page count)]. Every page carries its chapter's topic word so searches can find it."""
    doc = pymupdf.open()
    toc, n = [], 0
    for ctitle, count in chapters:
        toc.append([1, ctitle, n + 1])
        for _ in range(count):
            n += 1
            page = doc.new_page()
            if n not in blank_pages:
                page.insert_textbox(pymupdf.Rect(40, 40, 555, 800), f"{ctitle}\n" + LOREM.format(topic=f"This page is about {ctitle.split(':')[-1].strip()}."),
                                    fontsize=9)
    if bookmarks:
        doc.set_toc(toc)
    doc.set_metadata({"title": title, "author": author})
    doc.save(str(path))
    doc.close()
    return path


def make_scan(path: Path, pages: int = 3) -> Path:
    """A PDF with pictures only and no text layer."""
    doc = pymupdf.open()
    for _ in range(pages):
        page = doc.new_page()
        page.draw_rect(pymupdf.Rect(50, 50, 300, 300), fill=(0.5, 0.5, 0.5))
    doc.save(str(path))
    doc.close()
    return path


class FakeEmbedder:
    """Bag of words hashed into DIM numbers: texts that share words are close. Deterministic, no model, no network."""

    def __init__(self):
        self.calls = 0

    def _vec(self, text: str) -> np.ndarray:
        v = np.zeros(DIM, dtype=np.float32)
        for w in re.findall(r"[a-z0-9]+", text.lower()):
            v[int(hashlib.md5(w.encode()).hexdigest(), 16) % DIM] += 1
        n = np.linalg.norm(v)
        return v / n if n else v

    def documents(self, texts):
        self.calls += 1
        return np.stack([self._vec(t) for t in texts])

    queries = documents


class ScriptedBackend:
    """Returns queued replies (strings, or exceptions to raise) and records the prompts it was given."""

    def __init__(self, *replies, default=None):
        """`default` answers once the queue is empty (None = fail loudly, so a test notices a call it did not expect)."""
        self.replies, self.prompts, self.default = list(replies), [], default

    def complete(self, system, user, *, json_mode, images=None):
        self.prompts.append((system, user, json_mode))
        r = self.replies.pop(0) if self.replies else self.default
        assert r is not None, f"unexpected model call: {user[:80]!r}"
        if isinstance(r, Exception):
            raise r
        return Completion(text=r, prompt_tokens=10, completion_tokens=5, finish_reason="stop")


TRIAGE_OK = '{"book_type": "practical", "practicable": true, "likely_skills": ["Write a want-and-obstacle scene"], "reason": "Craft book with exercises."}'
TRIAGE_REF = '{"book_type": "theory", "practicable": false, "likely_skills": [], "reason": "Film theory with no exercises."}'

NO_SKILLS = '{"skills": []}'


# ---------- a model that understands which job it is asked to do

def skill_json(name, ids, *, concepts=("subtext",), prereqs=(), principles=2, level="spot"):
    return {"name": name, "description": f"You can {name.lower()}.", "practice_type": "scene",
            "principles": [{"principle": f"{name}: principle {i}", "test": f"Does the work meet {i}?", "chunk_id": ids[0]} for i in range(principles)],
            "concepts": [{"name": c, "level": level} for c in concepts], "prerequisites": list(prereqs)}


def concept_json(name, chunk_id, definition=None):
    d = definition or f"{name} is how a scene shows what a character will not say"
    return {"name": name, "definition": d, "example": "Made-up example: two people talk about the weather while one packs a bag.", "chunk_id": chunk_id,
            "questions": [{"level": lv, "prompt": f"{lv} question about {name}", "answer_key": f"{lv} answer"} for lv in ("define", "spot", "use")]}


class SmartBackend:
    """Answers by job. `skills(label, ids, existing)` -> list of skill dicts; `concepts(names, ids)` -> list of concept dicts;
    `merge(existing, candidate)` -> dict. `fail_on` = a job name that raises once (to test retry)."""

    def __init__(self, *, triage=TRIAGE_OK, skills=None, concepts=None, merge=None, recommend=None, fail_on=None, session=None):
        import collections
        self.session = session or {}
        self.users = []
        self.triage, self.skills, self.concepts, self.merge, self.recommend = triage, skills or (lambda *a: []), concepts, merge, recommend
        self.calls, self.fail_on, self.labels = collections.Counter(), fail_on, []

    def complete(self, system, user, *, json_mode, images=None):
        import json
        data = user.split('<data label="book text">')[-1] if '<data label="book text">' in user else ""
        ids = [int(x) for x in re.findall(r"^\[c(\d+)\] ", data, re.MULTILINE)]       # the instructions also mention "[c12]" as an example
        if "You decide whether a book can teach" in user:
            job, out = "triage", self.triage
        elif "You turn one part of a book" in user:
            job = "skill_extraction"
            label = re.search(r"^Part: (.*)$", user, re.MULTILINE).group(1)
            existing = re.search(r"do not repeat them\)\n(.*?)\n\n## The text", user, re.DOTALL).group(1)
            self.labels.append(label)
            out = json.dumps({"skills": self.skills(label, ids, existing)})
        elif "concept library" in user:
            job = "concept_extraction"
            names = re.findall(r"^- (.+)$", re.search(r"## Concepts to define\n(.*?)\n\n## What", user, re.DOTALL).group(1), re.MULTILINE)
            out = json.dumps({"concepts": (self.concepts or (lambda n, i: [concept_json(x, i[0]) for x in n]))(names, ids)})
        elif "Two descriptions of a skill" in user:
            job = "skill_merge"
            out = json.dumps((self.merge or (lambda e, c: {"same_skill": False}))(user, user))
        elif "You help a learner decide what to practice next" in user:
            job = "skill_recommendation"
            listed = [(int(i), n) for i, n in re.findall(r"^- id (\d+): (.+?):", user, re.MULTILINE)]
            out = json.dumps((self.recommend or (lambda listed, user: {"picks": []}))(listed, user))
        elif "## Phase: Diagnose, reading the learner" in user:
            job, out = "diagnose_eval", self._session("diagnose_eval", user)
        elif "## Phase: Diagnose\n" in user:
            job, out = "diagnose", self._session("diagnose", user)
        elif "## Phase: Learn just enough" in user:
            job, out = "teach", self._session("teach", user)
        elif "## Phase: Practice\n" in user:
            job, out = "practice_task", self._session("practice_task", user)
        elif "## Phase: Feedback\n" in user:
            job, out = "feedback", self._session("feedback", user)
        elif "## Phase: Check, judging one answer" in user:
            job, out = "concept_check", self._session("concept_check", user)
        elif "## Phase: Check, a hint" in user:
            job, out = "concept_hint", self._session("concept_hint", user)
        elif "## Phase: Check, a new example to spot" in user:
            job, out = "concept_spot", self._session("concept_spot", user)
        elif "## Phase: Check, a short re-teach" in user:
            job, out = "concept_reteach", self._session("concept_reteach", user)
        elif "A question from the learner" in user:
            job, out = "qa", self._session("qa", user)
        else:
            raise AssertionError(f"unknown job: {user[:80]}")
        self.users.append(user)
        self.calls[job] += 1
        if self.fail_on == job:
            self.fail_on = None
            from ai_tutor.llm.errors import LLMPausedError
            raise LLMPausedError("down")
        return Completion(text=out, prompt_tokens=1, completion_tokens=1, finish_reason="stop")


    def _session(self, job, user):
        import json
        h = self.session.get(job)
        cites = re.findall(r"^CITATION: (.+)$", user, re.MULTILINE)
        if callable(h):
            h = h(user, cites)
        return h if isinstance(h, str) else json.dumps(h)


def words(n: int, cite: str = "") -> str:
    """n words of filler, ending with a citation (the citation counts as words too, so n is approximate)."""
    return " ".join(["word"] * n) + (f" {cite}" if cite else "")


def fb_json(results=("followed", "partly"), quotes=("Mai reaches for the tin", "Grandma slides the tin"), *, mistakes=None, fixes=None, shown=(), since="", comments=None):
    """A feedback reply for a skill with len(results) principles."""
    out = {"principles": [{"n": i, "result": r, "quote": quotes[i - 1] if i - 1 < len(quotes) else "", "comment": (comments or {}).get(i, f"Comment {i}.")}
                          for i, r in enumerate(results, 1)],
           "concepts_shown": list(shown), "since_last": since, "summary": "model summary"}
    failing = [i for i, r in enumerate(results, 1) if r != "followed"]
    out["fixes"] = fixes if fixes is not None else [{"n": i, "fix": f"Fix principle {i}.", "example": ""} for i in failing[:2]]
    out["mistakes"] = mistakes if mistakes is not None else [{"n": i, "kind": "execution", "concept": None, "tag": f"mistake {i}"} for i in failing]
    return out
