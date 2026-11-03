from ai_tutor import app_settings
from ai_tutor.setup_check import check_dependencies, summarize

ALL = lambda name: f"/usr/bin/{name}"
NONE = lambda name: None
CFG = app_settings.LlmConfig("http://127.0.0.1:8080/v1", "some-model")


def run(**kw):
    base = {"llm_config": lambda: CFG, "which": ALL, "has_module": lambda n: True, "model_cached": lambda: True}
    return {c.id: c for c in check_dependencies(**{**base, **kw})}


def test_all_ready():
    r = run()
    assert {c.status for c in r.values()} == {"ready"}
    s = summarize(list(r.values()))
    assert s["can_continue"] and s["media_enabled"] and s["media_note"] is None


def test_missing_llm_blocks_with_a_fix():
    r = run(llm_config=lambda: None)
    assert r["llm"].status == "missing" and r["llm"].fix
    assert not summarize(list(r.values()))["can_continue"]


def test_every_missing_item_has_a_one_line_fix():
    r = run(llm_config=lambda: None, which=NONE, has_module=lambda n: False)
    for c in r.values():
        assert c.status == "missing" and c.fix and "\n" not in c.fix


def test_missing_media_tools_disable_only_media():
    for kw in ({"which": NONE}, {"has_module": lambda n: False}, {"model_cached": lambda: False}):
        s = summarize(list(run(**kw).values()))
        assert s["can_continue"] is True          # text learning still works
        assert s["media_enabled"] is False
        assert "Text practice still works" in s["media_note"]


def test_whisper_package_without_model_is_reported_separately():
    r = run(model_cached=lambda: False)
    assert r["whisper"].status == "missing" and "model" in r["whisper"].detail
    assert r["ffmpeg"].status == "ready"


def test_server_is_only_contacted_on_request():
    calls = []

    def v(cfg):
        calls.append(cfg)
        return "invalid"
    assert run(verify_llm=v)["llm"].status == "ready" and calls == []
    assert run(verify=True, verify_llm=v)["llm"].status == "invalid"
    assert calls == [CFG]


def test_unreachable_does_not_lock_the_user_out():
    r = run(verify=True, verify_llm=lambda c: "unreachable")
    assert r["llm"].status == "unreachable"
    assert summarize(list(r.values()))["can_continue"]


def test_config_needs_url_and_model_key_is_optional(monkeypatch):
    assert app_settings.llm_config() is None
    monkeypatch.setenv("LLM_BASE_URL", "http://lan:5000/v1/")
    assert app_settings.llm_config() is None                      # model still missing
    monkeypatch.setenv("LLM_MODEL", "qwen")
    assert app_settings.llm_config() == app_settings.LlmConfig("http://lan:5000/v1", "qwen", None)


def test_saved_settings_win_over_environment(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://env/v1")
    monkeypatch.setenv("LLM_MODEL", "env-model")
    app_settings.save(app_settings.AppSettings(llm_base_url="http://saved/v1", llm_model="saved-model", llm_api_key="k"))
    assert app_settings.llm_config() == app_settings.LlmConfig("http://saved/v1", "saved-model", "k")
