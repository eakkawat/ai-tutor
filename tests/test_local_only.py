"""CLAUDE.md: no hosting, login, analytics or telemetry."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BANNED = re.compile(r"sentry|posthog|mixpanel|segment\.|amplitude|google-analytics|gtag|datadog|telemetry", re.IGNORECASE)


def test_no_analytics_in_python_sources():
    for f in (ROOT / "ai_tutor").rglob("*.py"):
        assert not BANNED.search(f.read_text("utf-8")), f


def test_no_analytics_in_frontend_deps():
    pkg = json.loads((ROOT / "web" / "package.json").read_text("utf-8"))
    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    assert not [d for d in deps if BANNED.search(d)]
