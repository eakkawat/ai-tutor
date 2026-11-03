"""Skill and concept extraction (Flow 2, from "Extract skills" on). One chapter at a time; a retry skips chapters already done.

Per chapter: ask for skills with principle checklists → define the concepts they need (existing ones are linked, not defined again)
→ check each skill against the library for a match to merge → store. Everything the model says is checked in code: unknown passage ids
are dropped, a skill without 2 cited principles or without a concept is dropped.
"""
import logging
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
from pydantic import BaseModel, Field

from .. import skills as sk
from ..embeddings import Embedder, EmbeddingUnavailable, chunk_document
from ..llm.client import LLMClient
from ..llm.prompts import DATA_RULE, fence, load_prompt

log = logging.getLogger(__name__)

PART_CHARS = 24000          # about 7k tokens of book text per call
MAX_SKILLS_PER_PART = 3
MATCH_COSINE = 0.75         # a library skill this close to a new one is shown to the model as a possible match
CONCEPT_SAME_COSINE = 0.9   # a new definition this close to an existing concept's is the same concept
MIN_PRINCIPLES = 2


class PrincipleOut(BaseModel):
    principle: str
    test: str
    chunk_id: int


class ConceptRef(BaseModel):
    name: str
    level: Literal["spot", "use"] = "spot"


class SkillOut(BaseModel):
    name: str
    description: str
    practice_type: str = ""
    principles: list[PrincipleOut] = Field(default_factory=list)
    concepts: list[ConceptRef] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)


class SkillsOut(BaseModel):
    skills: list[SkillOut] = Field(default_factory=list)


class QuestionOut(BaseModel):
    level: Literal["define", "spot", "use"]
    prompt: str
    answer_key: str


class ConceptOut(BaseModel):
    name: str
    definition: str
    example: str
    chunk_id: int
    questions: list[QuestionOut] = Field(default_factory=list)


class ConceptsOut(BaseModel):
    concepts: list[ConceptOut] = Field(default_factory=list)


class MergeOut(BaseModel):
    same_skill: bool
    reason: str = ""
    add_principles: list[int] = Field(default_factory=list)


@dataclass
class Stats:
    added: int = 0            # new skills (active or waiting for review)
    pending: int = 0          # of those, waiting for the user
    merges: int = 0           # proposed merges waiting for the user
    merged_quietly: int = 0   # matches inside the same book, applied directly
    dropped: list[str] = field(default_factory=list)

    def message(self) -> str | None:
        parts = []
        if self.pending:
            parts.append(f"{self.pending} new skill{'s' if self.pending != 1 else ''} waiting for your review")
        if self.merges:
            parts.append(f"{self.merges} would merge into skills you already have")
        if not (self.added or self.merges or self.merged_quietly):
            return "No valid skills could be extracted from this book. You can try “Look for skills again”."
        return ". ".join(parts) + "." if parts else None


def units(db: sqlite3.Connection, source_id: int) -> list[tuple[str, list[sqlite3.Row]]]:
    out: dict[str, list[sqlite3.Row]] = {}
    for r in db.execute("SELECT * FROM chunk WHERE source_id = ? ORDER BY ord", (source_id,)):
        out.setdefault(r["label"] or r["title"] or "Book", []).append(r)
    return list(out.items())


def parts_of(chunks: list[sqlite3.Row], limit: int = PART_CHARS) -> list[list[sqlite3.Row]]:
    parts: list[list[sqlite3.Row]] = []
    cur: list[sqlite3.Row] = []
    size = 0
    for c in chunks:
        if cur and size + len(c["text"]) > limit:
            parts.append(cur)
            cur, size = [], 0
        cur.append(c)
        size += len(c["text"])
    if cur:
        parts.append(cur)
    return parts


def render_passages(chunks: list[sqlite3.Row]) -> str:
    return "\n\n".join(f"[c{c['id']}] (p. {c['page_start']}–{c['page_end']})\n{c['text']}" for c in chunks)


def _cos(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))


class Extractor:
    def __init__(self, db: sqlite3.Connection, source_id: int, domain: str, *, llm: LLMClient, embedder: Embedder | None, mode: str,
                 check: Callable[[], None] = lambda: None, say: Callable[[float, str], None] = lambda f, m: None):
        self.db, self.sid, self.domain, self.llm, self.embedder, self.mode, self.check, self.say = db, source_id, domain, llm, embedder, mode, check, say
        self.title = db.execute("SELECT title FROM source WHERE id = ?", (source_id,)).fetchone()[0]
        self.stats = Stats()
        self.prereqs: list[tuple[int, list[str]]] = []

    # ---------- the whole book
    def run(self) -> Stats:
        todo = [(label, ch) for label, ch in units(self.db, self.sid)
                if not self.db.execute("SELECT 1 FROM extraction_done WHERE source_id = ? AND unit_label = ?", (self.sid, label)).fetchone()]
        for i, (label, chunks) in enumerate(todo):
            self.check()
            self.say(i / max(len(todo), 1), f"Finding skills… {label} ({i + 1} of {len(todo)})")
            for part in parts_of(chunks):
                self.part(label, part)
            self.db.execute("INSERT OR IGNORE INTO extraction_done(source_id, unit_label) VALUES (?,?)", (self.sid, label))
            self.db.commit()
        self.resolve_prerequisites()
        sk.recompute_foundations(self.db)
        return self.stats

    # ---------- one part of a chapter
    def part(self, label: str, chunks: list[sqlite3.Row]) -> None:
        valid_ids = {c["id"] for c in chunks}
        prompt = load_prompt("skill_extraction")
        existing = [r["name"] for r in self.db.execute(
            "SELECT name FROM skill WHERE domain = ? AND status IN ('active','pending') AND merge_into IS NULL ORDER BY name LIMIT 60", (self.domain,))]
        out = self.llm.json(
            SkillsOut,
            prompt.render(rule=DATA_RULE, title=self.title, part=label, domain=self.domain, max_skills=MAX_SKILLS_PER_PART,
                          existing="\n".join(f"- {n}" for n in existing) or "(none yet)",
                          passages=fence("book text", render_passages(chunks))),
            prompt_version=prompt.version, source_id=self.sid, job="skill_extraction")
        good = [s for s in (self._clean(s, valid_ids) for s in out.skills[:MAX_SKILLS_PER_PART]) if s]
        if not good:
            return
        concept_ids = self.resolve_concepts(good, chunks, valid_ids)
        for s in good:
            links = [(concept_ids[sk.norm(c.name)], c.level) for c in s.concepts if sk.norm(c.name) in concept_ids]
            if not links:
                self.stats.dropped.append(f"{s.name}: no concept could be defined from the text")
                continue
            self.store(s, links, label)

    def _clean(self, s: SkillOut, valid_ids: set[int]) -> SkillOut | None:
        s.name, s.description = s.name.strip(), s.description.strip()
        s.principles = [p for p in s.principles if p.chunk_id in valid_ids and p.principle.strip() and p.test.strip()][:sk.MAX_PRINCIPLES]
        seen: set[str] = set()
        s.concepts = [c for c in s.concepts if c.name.strip() and not (sk.norm(c.name) in seen or seen.add(sk.norm(c.name)))][:5]
        if not s.name or not s.description:
            self.stats.dropped.append("a skill without a name or description")
            return None
        if len(s.principles) < MIN_PRINCIPLES:
            self.stats.dropped.append(f"{s.name}: fewer than {MIN_PRINCIPLES} principles with a real source")
            return None
        if not s.concepts:
            self.stats.dropped.append(f"{s.name}: no concepts")
            return None
        return s

    # ---------- concepts
    def resolve_concepts(self, skills: list[SkillOut], chunks: list[sqlite3.Row], valid_ids: set[int]) -> dict[str, int]:
        """name (normalised) -> concept id, for every concept that could be linked or defined."""
        by_name = {sk.norm(r["name"]): r["id"] for r in self.db.execute("SELECT id, name FROM concept")}
        found: dict[str, int] = {}
        wanted: dict[str, str] = {}
        for s in skills:
            for c in s.concepts:
                key = sk.norm(c.name)
                if key in by_name:
                    found[key] = by_name[key]
                else:
                    wanted.setdefault(key, c.name.strip())
        if not wanted:
            return found
        prompt = load_prompt("concept_extraction")
        uses = "\n".join(f"- {s.name}: {s.description}" for s in skills)
        out = self.llm.json(
            ConceptsOut,
            prompt.render(rule=DATA_RULE, title=self.title, names="\n".join(f"- {n}" for n in wanted.values()), skills=uses,
                          passages=fence("book text", render_passages(chunks))),
            prompt_version=prompt.version, source_id=self.sid, job="concept_extraction")
        fresh = [c for c in out.concepts if sk.norm(c.name) in wanted and c.chunk_id in valid_ids and c.definition.strip() and c.example.strip()]
        twins = self.find_twins(fresh)
        for c in fresh:
            key = sk.norm(c.name)
            if key in found:
                continue
            twin = twins.get(key)
            if twin:
                self.db.execute("INSERT OR IGNORE INTO concept_source(concept_id, chunk_id) VALUES (?,?)", (twin, c.chunk_id))
                self.db.commit()
                found[key] = twin
                continue
            qs = {q.level: (q.level, q.prompt.strip(), q.answer_key.strip()) for q in c.questions if q.prompt.strip() and q.answer_key.strip()}
            found[key] = sk.add_concept(self.db, name=c.name.strip(), definition=c.definition.strip(), example=c.example.strip(),
                                        chunk_ids=[c.chunk_id], questions=list(qs.values()))
        return found

    def find_twins(self, fresh: list[ConceptOut]) -> dict[str, int]:
        """A new definition very close to an existing concept's is that concept (linked, not duplicated)."""
        if not fresh or self.embedder is None:
            return {}
        old = self.db.execute("SELECT id, name, definition FROM concept").fetchall()
        if not old:
            return {}
        try:
            new_v = self.embedder.documents([chunk_document(c.name, c.definition) for c in fresh])
            old_v = self.embedder.documents([chunk_document(r["name"], r["definition"]) for r in old])
        except EmbeddingUnavailable:
            return {}
        out = {}
        for c, v in zip(fresh, new_v, strict=True):
            best = max(range(len(old)), key=lambda i: _cos(v, old_v[i]))
            if _cos(v, old_v[best]) >= CONCEPT_SAME_COSINE:
                out[sk.norm(c.name)] = old[best]["id"]
        return out

    # ---------- storing and matching
    def store(self, s: SkillOut, links: list[tuple[int, str]], label: str) -> None:
        principles = [(p.principle.strip(), p.test.strip(), p.chunk_id) for p in s.principles]
        match = self.find_match(s)
        if match is not None:
            target = match
            decision = self.ask_merge(target, s)
            if decision and decision.same_skill:
                same_book = target["source_id"] == self.sid
                keep = [principles[i - 1] for i in decision.add_principles if 1 <= i <= len(principles)]
                if same_book or not keep:
                    sk.add_principles(self.db, target["id"], keep)
                    for _, _, cid in principles:
                        self.db.execute("INSERT OR IGNORE INTO skill_source(skill_id, chunk_id) VALUES (?,?)", (target["id"], cid))
                    for cid, lvl in links:
                        self.db.execute("INSERT OR IGNORE INTO skill_concept(skill_id, concept_id, required_level) VALUES (?,?,?)", (target["id"], cid, lvl))
                    self.db.commit()
                    self.stats.merged_quietly += 1
                    return
                sid = sk.add_skill(self.db, domain=self.domain, name=s.name, description=s.description, practice_type=s.practice_type or None,
                                   source_id=self.sid, unit_label=label, status="pending", principles=keep, concepts=links,
                                   merge_into=target["id"], merge_note=decision.reason or None)
                self.stats.merges += 1
                self.prereqs.append((sid, s.prerequisites))
                return
        status = "active" if self.mode == "auto" else "pending"
        sid = sk.add_skill(self.db, domain=self.domain, name=s.name, description=s.description, practice_type=s.practice_type or None,
                           source_id=self.sid, unit_label=label, status=status, principles=principles, concepts=links)
        self.stats.added += 1
        self.stats.pending += status == "pending"
        self.prereqs.append((sid, s.prerequisites))

    def find_match(self, s: SkillOut) -> sqlite3.Row | None:
        rows = self.db.execute("SELECT id, name, description, source_id FROM skill WHERE domain = ? AND status IN ('active','pending') AND merge_into IS NULL",
                               (self.domain,)).fetchall()
        if not rows:
            return None
        for r in rows:                                    # same name: no need to ask an embedding
            if sk.norm(r["name"]) == sk.norm(s.name):
                return r
        if self.embedder is None:
            return None
        try:
            q = self.embedder.queries([chunk_document(s.name, s.description)])[0]
            docs = self.embedder.documents([chunk_document(r["name"], r["description"]) for r in rows])
        except EmbeddingUnavailable:
            return None
        best = max(range(len(rows)), key=lambda i: _cos(q, docs[i]))
        return rows[best] if _cos(q, docs[best]) >= MATCH_COSINE else None

    def ask_merge(self, target: sqlite3.Row, s: SkillOut) -> MergeOut | None:
        prompt = load_prompt("skill_merge")
        existing = sk.skill_detail(self.db, target["id"])
        ex = f"{existing['name']}: {existing['description']}\n" + "\n".join(f"- {p['principle']}" for p in existing["principles"])
        cand = f"{s.name}: {s.description}\n" + "\n".join(f"{i}. {p.principle}" for i, p in enumerate(s.principles, 1))
        return self.llm.json(MergeOut, prompt.render(rule=DATA_RULE, existing=fence("existing skill", ex), candidate=fence("new skill", cand)),
                             prompt_version=prompt.version, source_id=self.sid, job="skill_merge")

    def resolve_prerequisites(self) -> None:
        """Names the model gave become links to skills in the same domain; names that match nothing are dropped."""
        names = {sk.norm(r["name"]): r["id"] for r in self.db.execute(
            "SELECT id, name FROM skill WHERE domain = ? AND status IN ('active','pending') AND merge_into IS NULL", (self.domain,))}
        for sid, wanted in self.prereqs:
            for w in wanted:
                pid = names.get(sk.norm(w))
                if pid and pid != sid:
                    self.db.execute("INSERT OR IGNORE INTO skill_prereq(skill_id, prereq_skill_id) VALUES (?,?)", (sid, pid))
        self.db.commit()
