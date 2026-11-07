"""Report generation and progress analytics (read-only queries)."""
from __future__ import annotations

import json
from collections import Counter

STRONG = 70  # skill % at or above this is a strength
WEAK = 60    # skill % below this is a weak area


def _loads(value) -> list:
    try:
        return json.loads(value) if value else []
    except (TypeError, ValueError):
        return []


def get_interview(db, interview_id: int, user_id: int):
    """Return the interview row only if it belongs to this user."""
    return db.execute("SELECT * FROM interviews WHERE id = ? AND user_id = ?", (interview_id, user_id)).fetchone()


def build_report(db, interview) -> dict:
    rows = db.execute(
        """SELECT it.*, q.text AS question, q.subject, q.difficulty, q.reference_answer
           FROM interview_items it JOIN questions q ON q.id = it.question_id
           WHERE it.interview_id = ? ORDER BY it.position""",
        (interview["id"],),
    ).fetchall()

    items = []
    by_skill: dict[str, list[float]] = {}
    missing_counter: Counter = Counter()
    sum_relevance = sum_technical = sum_completeness = sum_clarity = 0
    answered_count = 0
    
    for r in rows:
        answered = r["answered_at"] is not None
        item = {
            "position": r["position"], 
            "question": r["question"],
            "question_text": r["question"],  # Add for template compatibility
            "subject": r["subject"],
            "difficulty": r["difficulty"], 
            "answered": answered, 
            "transcript": r["transcript"] or "",
            "duration_sec": r["duration_sec"] or 0, 
            "score": r["score"] or 0,
            "dimensions": {k: r[k] for k in ("relevance", "technical_correctness", "completeness", "clarity", "key_concepts")},
            "covered": _loads(r["covered_concepts"]), 
            "missing": _loads(r["missing_concepts"]),
            "strengths": _loads(r["strengths"]), 
            "improvements": _loads(r["improvements"]),
            "feedback": r["feedback"] or "", 
            "suggestion": r["suggestion"] or "",
            "evaluator": r["evaluator"], 
            "reference_answer": r["reference_answer"],
        }
        items.append(item)
        if answered:
            by_skill.setdefault(r["subject"], []).append(r["score"] or 0)
            if (r["score"] or 0) < 7:
                for concept in item["missing"]:
                    missing_counter[(r["subject"], concept)] += 1
            # Accumulate dimension scores for averages
            sum_relevance += r["relevance"] or 0
            sum_technical += r["technical_correctness"] or 0
            sum_completeness += r["completeness"] or 0
            sum_clarity += r["clarity"] or 0
            answered_count += 1

    skills = [{"skill": s, "score": round(sum(v) / len(v) * 10)} for s, v in by_skill.items()]
    skills.sort(key=lambda x: -x["score"])
    answered_items = [i for i in items if i["answered"]]
    
    # Calculate average dimension scores
    avg_relevance = (sum_relevance / answered_count) if answered_count > 0 else 0
    avg_technical = (sum_technical / answered_count) if answered_count > 0 else 0
    avg_completeness = (sum_completeness / answered_count) if answered_count > 0 else 0
    avg_clarity = (sum_clarity / answered_count) if answered_count > 0 else 0
    
    report = {
        "interview": dict(interview),
        "item_list": items,  # Renamed from 'items' to avoid dict.items() collision
        "skills": skills,
        "strong_areas": [s for s in skills if s["score"] >= STRONG],
        "weak_areas": [s for s in skills if s["score"] < WEAK],
        "recommended": [{"skill": s, "topic": c} for (s, c), _ in missing_counter.most_common(6)],
        "total_duration_sec": sum(i["duration_sec"] for i in answered_items),
        "answered": len(answered_items),
        "evaluators": sorted({i["evaluator"] for i in answered_items if i["evaluator"]}),
        # Add top-level fields for template access
        "category": interview["category"],
        "role": interview["role"],
        "difficulty": interview["difficulty"],
        "started_at": interview["started_at"],
        "overall_score": interview["overall_score"] or 0,
        "avg_relevance": avg_relevance,
        "avg_technical": avg_technical,
        "avg_completeness": avg_completeness,
        "avg_clarity": avg_clarity,
    }
    return report


def list_history(db, user_id: int) -> list[dict]:
    rows = db.execute(
        """SELECT i.*, (SELECT COALESCE(SUM(duration_sec), 0) FROM interview_items WHERE interview_id = i.id) AS duration_sec
           FROM interviews i WHERE i.user_id = ? ORDER BY i.id DESC""",
        (user_id,),
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["skills"] = _loads(r["skills"])
        out.append(d)
    return out


def progress_series(db, user_id: int) -> dict:
    """Per-skill and overall score (0-100) for every completed interview, oldest first."""
    rows = db.execute(
        """SELECT i.id AS interview_id, i.finished_at, i.overall_score, q.subject, AVG(it.score) * 10 AS pct
           FROM interviews i
           JOIN interview_items it ON it.interview_id = i.id AND it.answered_at IS NOT NULL
           JOIN questions q ON q.id = it.question_id
           WHERE i.user_id = ? AND i.status = 'completed'
           GROUP BY i.id, q.subject ORDER BY i.finished_at, i.id""",
        (user_id,),
    ).fetchall()

    skills: dict[str, list[dict]] = {}
    overall: dict[int, dict] = {}
    for r in rows:
        points = skills.setdefault(r["subject"], [])
        points.append({"attempt": len(points) + 1, "interview_id": r["interview_id"],
                       "date": r["finished_at"], "score": round(r["pct"])})
        overall.setdefault(r["interview_id"], {"interview_id": r["interview_id"], "date": r["finished_at"],
                                               "score": round(r["overall_score"] or 0)})
    overall_list = list(overall.values())
    for n, point in enumerate(overall_list, 1):
        point["attempt"] = n
    return {"skills": skills, "overall": overall_list}
