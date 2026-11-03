import stat

from ai_tutor import app_settings

READY = {"which": lambda n: "/x", "has_module": lambda n: True, "model_cached": lambda: True}
BODY = {"base_url": "http://127.0.0.1:8080/v1/", "model": " some-model ", "api_key": ""}


def test_status_without_llm(make_client):
    with make_client(check_kwargs=READY) as c:
        s = c.get("/api/setup/status").json()
    assert s["can_continue"] is False and s["checks"][0]["id"] == "llm" and s["checks"][0]["status"] == "missing"


def test_save_valid_settings_key_optional(make_client):
    with make_client(check_kwargs=READY, verify_llm=lambda c: "ok") as c:
        r = c.post("/api/setup/llm", json=BODY)
        assert r.status_code == 200 and r.json()["can_continue"] is True
    cfg = app_settings.llm_config()
    assert cfg == app_settings.LlmConfig("http://127.0.0.1:8080/v1", "some-model", None)
    assert stat.S_IMODE(app_settings.settings_path().stat().st_mode) == 0o600


def test_rejected_key_is_not_saved(make_client):
    with make_client(check_kwargs=READY, verify_llm=lambda c: "invalid") as c:
        r = c.post("/api/setup/llm", json={**BODY, "api_key": "bad"})
    assert r.status_code == 400 and r.json()["detail"]["field"] == "api_key"
    assert app_settings.llm_config() is None


def test_offline_save_keeps_settings_and_says_unverified(make_client):
    with make_client(check_kwargs=READY, verify_llm=lambda c: "unreachable") as c:
        r = c.post("/api/setup/llm", json=BODY).json()
    assert r["can_continue"] is True and r["checks"][0]["status"] == "unreachable"
    assert app_settings.llm_config() is not None


def test_bad_url_and_empty_model_rejected(make_client):
    with make_client() as c:
        r = c.post("/api/setup/llm", json={**BODY, "base_url": "localhost:8080"})
        assert r.status_code == 400 and r.json()["detail"]["field"] == "base_url"
        r = c.post("/api/setup/llm", json={**BODY, "model": "  "})
        assert r.status_code == 400 and r.json()["detail"]["field"] == "model"


def test_home_empty_library(make_client):
    with make_client() as c:
        assert c.get("/api/home").json()["state"] == "empty_library"


def test_home_states(make_client):
    with make_client() as c:
        db = c.app.state.db
        db.execute("INSERT INTO source(title) VALUES ('[Book A]')")
        db.commit()
        assert c.get("/api/home").json()["state"] == "no_active_skill"
        db.execute("INSERT INTO skill(domain,name,description) VALUES ('Screenwriting','Write a want and obstacle scene','d')")
        db.execute("INSERT INTO learner_skill(skill_id,status) VALUES (1,'active')")
        db.commit()
        h = c.get("/api/home").json()
        assert h["state"] == "active_skill" and h["active_skill"]["name"].startswith("Write")
        db.execute("INSERT INTO skill(domain,name,description) VALUES ('Screenwriting','Cut on action','d')")
        db.execute("INSERT INTO learner_skill(skill_id,status) VALUES (2,'passed')")
        db.execute("INSERT INTO review_item(skill_id,question,answer,due_at) VALUES (2,'q','a',datetime('now','-1 day'))")
        db.commit()
        h = c.get("/api/home").json()
        assert h["state"] == "reviews_due" and h["reviews_due"] == 1
