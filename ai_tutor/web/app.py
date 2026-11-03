"""FastAPI app. Local only: bind it to 127.0.0.1 (see Makefile)."""
import sqlite3
from collections.abc import Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .. import app_settings, setup_check
from ..config import Paths
from ..config import paths as default_paths
from ..embeddings import get_embedder
from ..home import home_state
from ..llm.client import LLMClient
from ..session import utcnow as session_clock
from ..store.conn import open_db
from ..worker import Worker
from .library_api import router as library_router
from .projects_api import router as projects_router
from .sessions_api import router as sessions_router
from .skills_api import router as skills_router


class LlmIn(BaseModel):
    base_url: str
    model: str
    api_key: str | None = None


def create_app(
    *,
    data_paths: Paths | None = None,
    check_kwargs: dict | None = None,
    verify_llm: Callable[[app_settings.LlmConfig], setup_check.KeyVerdict] = setup_check.verify_llm,
    embedder: Callable[[], object | None] = get_embedder,
    llm_client: Callable[[int], LLMClient | None] | None = None,
    resume: bool = True,
    clock: Callable[[], object] = session_clock,
) -> FastAPI:
    """`check_kwargs`, `verify_llm`, `embedder` and `llm_client` let tests replace the network, the installed tools and the models."""
    kw = dict(check_kwargs or {})

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        p = (data_paths or default_paths()).ensure()
        app.state.paths = p
        app.state.clock = clock
        app.state.db = open_db(p.db)
        app.state.embedder = embedder
        app.state.llm_factory = llm_client or (lambda sid: LLMClient.for_job("triage") if app_settings.llm_config() else None)
        app.state.worker = Worker(p.db, embedder_factory=embedder, llm_factory=app.state.llm_factory)
        if resume:
            app.state.worker.resume_interrupted(app.state.db)
        yield
        app.state.worker.shutdown()
        app.state.db.close()

    app = FastAPI(title="AI Tutor", lifespan=lifespan)
    app.include_router(library_router)
    app.include_router(skills_router)
    app.include_router(projects_router)
    app.include_router(sessions_router)

    def status(verify: bool) -> dict:
        return setup_check.summarize(setup_check.check_dependencies(verify=verify, verify_llm=verify_llm, **kw))

    @app.get("/api/setup/status")
    def setup_status(verify: bool = False) -> dict:
        return status(verify)

    @app.post("/api/setup/llm")
    def save_llm(body: LlmIn) -> dict:
        base, model, key = body.base_url.strip().rstrip("/"), body.model.strip(), (body.api_key or "").strip() or None
        if not base.startswith(("http://", "https://")):
            raise HTTPException(400, {"message": "The server URL must start with http:// or https://.", "field": "base_url"})
        if not model:
            raise HTTPException(400, {"message": "Enter the model name.", "field": "model"})
        cfg = app_settings.LlmConfig(base, model, key)
        verdict = verify_llm(cfg)
        if verdict == "invalid":
            raise HTTPException(400, {"message": "The server rejected this API key. Check it and try again.", "field": "api_key"})
        # unreachable: keep the settings and say they are unverified
        app_settings.save(app_settings.AppSettings(llm_base_url=base, llm_model=model, llm_api_key=key))
        return setup_check.summarize(
            setup_check.check_dependencies(verify=True, llm_config=lambda: cfg, verify_llm=lambda _c: verdict, **kw)
        )

    @app.get("/api/home")
    def home() -> dict:
        db: sqlite3.Connection = app.state.db
        return home_state(db)

    return app


app = create_app()
