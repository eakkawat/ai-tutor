"""Shared pieces for the session tests: a controllable clock, scripted model replies, and steps that take a session to a phase."""
from datetime import UTC, datetime, timedelta

from helpers import SmartBackend, fb_json, words  # noqa: F401

T0 = datetime(2026, 11, 3, 10, 0, 0, tzinfo=UTC)
CITE1, CITE2 = "[Book A, ch. 3, p. 41]", "[Book A, ch. 4, p. 60]"


class Clock:
    def __init__(self):
        self.now = T0

    def __call__(self):
        return self.now

    def tick(self, **kw):
        self.now += timedelta(**kw)


def wait(env, svc, minutes):
    """Time passes with the screen open: the browser sends a heartbeat every so often."""
    for _ in range(int(minutes)):
        env.clock.tick(minutes=1)
        svc.act(env.sid, "heartbeat")


def eval_all(followed=True, evidence="quote"):
    return lambda u, c: {"principles": [{"n": 1, "result": "followed" if followed else "partly", "evidence": evidence},
                                        {"n": 2, "result": "followed" if followed else "not", "evidence": evidence}],
                         "can_do": "You can set the scene.", "gap": "The want shows up too late.", "level": 2 if not followed else 3}


def good_lesson(u, c):
    return {"title": "State the want early", "body": f"A scene needs a want first {c[0]}. The obstacle must push back {c[1]}.", "example": "Made-up example: a heist crew."}


WORK = "INT. KITCHEN - NIGHT\nMai reaches for the tin on the top shelf.\nGrandma slides the tin behind the rice jar."

PRACTICE = {"title": "Rewrite the kitchen scene", "instructions": "Mai wants the recipe tin. Make it clear early.", "support": "beat template",
            "template": ["Show the want", "First block", "New tactic"], "minutes": 20}


def script(**over):
    s = {"diagnose": {"task": "Write three lines where Mai wants the recipe tin."}, "diagnose_eval": eval_all(False), "teach": good_lesson,
         "practice_task": PRACTICE, "feedback": lambda u, c: fb_json(), "qa": lambda u, c: {"answer": f"The want drives the scene {c[0]}. Back to your task.", "drift": False}}
    s.update(over)
    return s


def to_learn(env, svc=None):
    svc = svc or env.make()
    svc.act(env.sid, "begin")
    svc.act(env.sid, "answer", "Mai: Give me the tin.")
    svc.act(env.sid, "advance")
    return svc


def master(env, level="spot"):
    env.db.execute("UPDATE concept_mastery SET level = ?", (level,))
    env.db.commit()


def to_practice(env, svc=None):
    svc = to_learn(env, svc)
    svc.act(env.sid, "continue")
    master(env)
    svc.act(env.sid, "unlock")
    return svc


