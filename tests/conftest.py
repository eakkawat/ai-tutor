import pytest
from fastapi.testclient import TestClient

from ai_tutor.config import Paths
from ai_tutor.web.app import create_app


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    """Never touch the real ~/.config/ai-tutor or a real server."""
    monkeypatch.setenv("AI_TUTOR_HOME", str(tmp_path / "home"))
    for v in ("LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY"):
        monkeypatch.delenv(v, raising=False)


@pytest.fixture
def make_client(tmp_path):
    def make(**kw):
        return TestClient(create_app(data_paths=Paths(root=tmp_path / "data"), **kw))
    return make


# ---------- a session ready to be taught: one skill with two principles and two concepts, a project, and a started session

@pytest.fixture
def env(tmp_path):
    from helpers import FakeEmbedder, SmartBackend
    from session_helpers import Clock, script

    from ai_tutor import picker, projects
    from ai_tutor import skills as sk
    from ai_tutor.llm.client import LLMClient
    from ai_tutor.session import SessionService
    from ai_tutor.store.conn import open_db
    db = open_db(tmp_path / "a.db")
    db.execute("INSERT INTO source(id, title) VALUES (1, 'Book A')")
    for cid, label, page, text in [(1, "Ch. 3", 41, "A scene needs a want and an obstacle."), (2, "Ch. 4", 60, "Each exchange shifts who has the upper hand."),
                                   (3, "Ch. 5", 70, "Subtext is what a character means but does not say.")]:
        db.execute("INSERT INTO chunk(id, source_id, label, title, chapter, page_start, page_end, text, ord) VALUES (?,1,?,?,?,?,?,?,?)",
                   (cid, label, label, label, page, page, text, cid))
    db.commit()
    c1 = sk.add_concept(db, name="want", definition="what a character is after", example="Made-up example", chunk_ids=[1],
                        questions=[("spot", "Which line shows a want?", "B")])
    c2 = sk.add_concept(db, name="obstacle", definition="what pushes back", example="Made-up example", chunk_ids=[2], questions=[("define", "What is an obstacle?", "force")])
    skill = sk.add_skill(db, domain="screenwriting", name="Write a want and obstacle scene", description="You can write a scene driven by a want.",
                         practice_type="scene", source_id=1, unit_label=None, status="active",
                         principles=[("The want is clear in the first beat", "Can you name the want after beat one?", 1), ("The obstacle pushes back", "Does it answer each try?", 2)],
                         concepts=[(c1, "spot"), (c2, "spot")])
    other = sk.add_skill(db, domain="screenwriting", name="Cut on action", description="You can cut on action.", practice_type="edit", source_id=1,
                         unit_label=None, status="active", principles=[("Cut during the movement", "t", 3), ("Match the eyeline", "t2", 3)], concepts=[])
    p = projects.create(db, name="Grandma's Kitchen", description="A short film about my grandmother", good_enough="A stranger gets it", minutes_per_session=25)
    started = picker.start_skill(db, p, skill)
    clock = Clock()
    log = tmp_path / "feedback.log"

    def make(backend=None, **kw):
        be = backend or SmartBackend(session=script())
        svc = SessionService(db, llm=LLMClient("t", be, model="m"), embedder=FakeEmbedder(), clock=clock, log_path=log, **kw)
        svc.be = be
        return svc
    return type("Env", (), {"db": db, "make": make, "sid": started["session_id"], "skill": skill, "other": other, "clock": clock, "log": log, "c1": c1, "c2": c2})



