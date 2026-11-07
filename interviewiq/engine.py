"""Interview engine: question selection."""
from __future__ import annotations

import random

DIFFICULTIES = ["basic", "intermediate", "advanced"]
RECENT_INTERVIEWS = 3  # avoid repeating questions from a student's last few interviews when possible


def _distance(a: str, b: str) -> int:
    return abs(DIFFICULTIES.index(a) - DIFFICULTIES.index(b))


def available_subjects(db) -> list[str]:
    rows = db.execute("SELECT DISTINCT subject FROM questions WHERE category = 'technical' ORDER BY subject").fetchall()
    return [r["subject"] for r in rows]


def recently_seen(db, user_id: int) -> set[int]:
    rows = db.execute(
        """SELECT it.question_id FROM interview_items it
           WHERE it.interview_id IN (SELECT id FROM interviews WHERE user_id = ? ORDER BY id DESC LIMIT ?)""",
        (user_id, RECENT_INTERVIEWS),
    ).fetchall()
    return {r["question_id"] for r in rows}


def select_questions(db, user_id: int, skills: list[str], difficulty: str, n: int,
                     rng: random.Random | None = None) -> list[int]:
    """Pick up to n question ids, spread evenly across skills.

    Within a skill, questions at the requested difficulty come first, then neighbouring difficulties;
    questions the student saw recently are pushed back; ties are broken randomly.
    """
    rng = rng or random.Random()
    seen = recently_seen(db, user_id)
    pools: dict[str, list[int]] = {}
    for skill in skills:
        rows = db.execute("SELECT id, difficulty FROM questions WHERE subject = ?", (skill,)).fetchall()
        ranked = sorted(rows, key=lambda r: (_distance(r["difficulty"], difficulty), r["id"] in seen, rng.random()))
        pools[skill] = [r["id"] for r in ranked]

    order = list(pools)
    rng.shuffle(order)
    picked: list[int] = []
    while len(picked) < n and any(pools.values()):
        for skill in order:
            if pools[skill] and len(picked) < n:
                picked.append(pools[skill].pop(0))
    return picked
