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
