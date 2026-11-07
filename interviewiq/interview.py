"""Interview pages and JSON API: dashboard, start, next question, submit answer, report, history, progress."""
import json
from flask import (Blueprint, abort, current_app, flash, g, jsonify, redirect, render_template,
                   request, url_for)

from . import engine, reports, transcribe
from .auth import login_required
from .db import get_db, utcnow

bp = Blueprint("interview", __name__)

ROLES = ["Software Developer", "Backend Developer", "Frontend Developer", "Data Analyst", "ML Engineer"]
INTERVIEW_TYPES = {"technical": "Technical Interview", "hr": "HR Interview"}
MIN_Q, MAX_Q, DEFAULT_Q = 3, 10, 5


@bp.route("/")
def index():
    return redirect(url_for("interview.dashboard") if g.user else url_for("auth.login"))


@bp.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    history = reports.list_history(db, g.user["id"])
    completed = [h for h in history if h["status"] == "completed"]
    in_progress = next((h for h in history if h["status"] == "in_progress"), None)
    return render_template(
        "dashboard.html",
        subjects=engine.available_subjects(db), roles=ROLES, difficulties=engine.DIFFICULTIES,
        interview_types=INTERVIEW_TYPES, recent=history[:5], in_progress=in_progress,
        stats={
            "count": len(completed),
            "best": max((h["overall_score"] for h in completed), default=None),
            "latest": completed[0]["overall_score"] if completed else None,
        },
        default_q=DEFAULT_Q, min_q=MIN_Q, max_q=MAX_Q,
    )


@bp.route("/interview/start", methods=["POST"])
@login_required
def start():
    db = get_db()
    itype = request.form.get("interview_type", "technical")
    role = request.form.get("role", ROLES[0])
    difficulty = request.form.get("difficulty", "intermediate")
    try:
        n = int(request.form.get("num_questions", DEFAULT_Q))
    except ValueError:
        n = DEFAULT_Q
    n = max(MIN_Q, min(MAX_Q, n))

    if itype not in INTERVIEW_TYPES or difficulty not in engine.DIFFICULTIES or role not in ROLES:
        flash("Please choose valid interview options.", "danger")
        return redirect(url_for("interview.dashboard"))

    if itype == "hr":
        skills = ["HR"]
    else:
        valid = set(engine.available_subjects(db))
        skills = [s for s in request.form.getlist("skills") if s in valid]
        if not skills:
            flash("Pick at least one skill area.", "danger")
            return redirect(url_for("interview.dashboard"))

    question_ids = engine.select_questions(db, g.user["id"], skills, difficulty, n)
    if not question_ids:
        flash("No questions are available for that selection yet.", "danger")
        return redirect(url_for("interview.dashboard"))

    cur = db.execute(
        """INSERT INTO interviews (user_id, category, role, difficulty, skills, status, started_at, total_questions)
           VALUES (?, ?, ?, ?, ?, 'in_progress', ?, ?)""",
        (g.user["id"], itype, role, difficulty, json.dumps(skills), utcnow(), len(question_ids)),
    )
    interview_id = cur.lastrowid
    db.executemany(
        "INSERT INTO interview_items (interview_id, position, question_id) VALUES (?, ?, ?)",
        [(interview_id, pos, qid) for pos, qid in enumerate(question_ids, 1)],
    )
    db.commit()
    return redirect(url_for("interview.room", interview_id=interview_id))


def _own_interview_or_404(interview_id: int):
    interview = reports.get_interview(get_db(), interview_id, g.user["id"])
    if interview is None:
        abort(404, description="Interview not found.")
    return interview


@bp.route("/interview/<int:interview_id>")
@login_required
def room(interview_id):
    interview = _own_interview_or_404(interview_id)
    if interview["status"] == "completed":
        return redirect(url_for("interview.report", interview_id=interview_id))
    return render_template("interview.html", interview=interview, interview_types=INTERVIEW_TYPES)


def _pending_item(db, interview_id: int):
    return db.execute(
        """SELECT it.id, it.position, it.question_id, q.text, q.subject, q.difficulty, q.topic,
                  q.expected_concepts, q.reference_answer, q.evaluation_criteria
           FROM interview_items it JOIN questions q ON q.id = it.question_id
           WHERE it.interview_id = ? AND it.answered_at IS NULL ORDER BY it.position LIMIT 1""",
        (interview_id,),
    ).fetchone()


@bp.route("/api/interview/<int:interview_id>/next")
@login_required
def next_question(interview_id):
    interview = _own_interview_or_404(interview_id)
    if interview["status"] == "completed":
        return jsonify(done=True, report_url=url_for("interview.report", interview_id=interview_id))
    item = _pending_item(get_db(), interview_id)
    if item is None:  # defensive: everything answered but not finalised
        _finalise(get_db(), interview)
        return jsonify(done=True, report_url=url_for("interview.report", interview_id=interview_id))
    # never send the reference answer or expected concepts to the browser
    return jsonify(
        done=False, position=item["position"], total=interview["total_questions"],
        question={"text": item["text"], "subject": item["subject"], "difficulty": item["difficulty"]},
    )


def _finalise(db, interview) -> None:
    avg = db.execute(
        "SELECT AVG(score) AS a FROM interview_items WHERE interview_id = ? AND answered_at IS NOT NULL",
        (interview["id"],),
    ).fetchone()["a"] or 0.0
    db.execute(
        "UPDATE interviews SET status = 'completed', finished_at = ?, overall_score = ? WHERE id = ?",
        (utcnow(), round(avg * 10, 1), interview["id"]),
    )
    db.commit()


@bp.route("/api/interview/<int:interview_id>/answer", methods=["POST"])
@login_required
def submit_answer(interview_id):
    db = get_db()
    interview = _own_interview_or_404(interview_id)
    if interview["status"] == "completed":
        return jsonify(error="This interview is already finished."), 409

    payload = request.get_json(silent=True) or {}
    transcript = payload.get("transcript", "")
    if not isinstance(transcript, str):
        return jsonify(error="Transcript must be text."), 400
    transcript = transcript.strip()[: current_app.config["MAX_TRANSCRIPT_CHARS"]]
    try:
        duration = max(0, min(3600, int(payload.get("duration_sec", 0))))
    except (TypeError, ValueError):
        duration = 0

    item = _pending_item(db, interview_id)
    if item is None:
        return jsonify(error="No question is waiting for an answer."), 409

    question = {
        "text": item["text"], "subject": item["subject"], "difficulty": item["difficulty"],
        "expected_concepts": json.loads(item["expected_concepts"]),
        "reference_answer": item["reference_answer"], "evaluation_criteria": item["evaluation_criteria"],
    }
    result = current_app.extensions["evaluator"].evaluate(question, transcript)

    cur = db.execute(
        """UPDATE interview_items SET transcript = ?, duration_sec = ?, score = ?, relevance = ?,
               technical_correctness = ?, completeness = ?, clarity = ?, key_concepts = ?,
               covered_concepts = ?, missing_concepts = ?, strengths = ?, improvements = ?,
               feedback = ?, suggestion = ?, evaluator = ?, answered_at = ?
           WHERE id = ? AND answered_at IS NULL""",
        (transcript, duration, result["score"], result["relevance"], result["technical_correctness"],
         result["completeness"], result["clarity"], result["key_concepts"],
         json.dumps(result["covered_concepts"]), json.dumps(result["missing_concepts"]),
         json.dumps(result["strengths"]), json.dumps(result["improvements"]),
         result["feedback"], result["suggestion"], result["evaluator"], utcnow(), item["id"]),
    )
    if cur.rowcount == 0:  # a double submit raced us
        db.rollback()
        return jsonify(error="That question was already answered."), 409

    remaining = db.execute(
        "SELECT COUNT(*) AS c FROM interview_items WHERE interview_id = ? AND answered_at IS NULL", (interview_id,)
    ).fetchone()["c"]
    db.commit()
    done = remaining == 0
    if done:
        _finalise(db, interview)

    return jsonify(
        done=done, position=item["position"], total=interview["total_questions"],
        report_url=url_for("interview.report", interview_id=interview_id) if done else None,
        evaluation={k: result[k] for k in (
            "score", "relevance", "technical_correctness", "completeness", "clarity", "key_concepts",
            "covered_concepts", "missing_concepts", "strengths", "improvements", "feedback", "suggestion",
            "evaluator")},
    )


@bp.route("/interview/<int:interview_id>/report")
@login_required
def report(interview_id):
    interview = _own_interview_or_404(interview_id)
    if interview["status"] != "completed":
        return redirect(url_for("interview.room", interview_id=interview_id))
    return render_template("report.html", r=reports.build_report(get_db(), interview),
                           interview_types=INTERVIEW_TYPES)


@bp.route("/history")
@login_required
def history():
    return render_template("history.html", history=reports.list_history(get_db(), g.user["id"]),
                           interview_types=INTERVIEW_TYPES)


@bp.route("/api/progress")
@login_required
def progress():
    return jsonify(reports.progress_series(get_db(), g.user["id"]))


@bp.route("/api/transcribe", methods=["POST"])
@login_required
def transcribe_audio():
    """Transcribe uploaded audio using Groq Whisper API."""
    # Check if audio file is present
    if "audio" not in request.files:
        return jsonify(error="No audio file provided"), 400
    
    audio_file = request.files["audio"]
    if not audio_file.filename:
        return jsonify(error="No audio file selected"), 400
    
    # Validate file
    try:
        # Get file size by seeking to end
        audio_file.seek(0, 2)  # Seek to end
        size = audio_file.tell()
        audio_file.seek(0)  # Seek back to start
        
        transcribe.validate_audio_file(audio_file.filename, size)
    except transcribe.TranscriptionError as exc:
        return jsonify(error=str(exc)), 400
    
    # Save to temporary file
    temp_path = None
    try:
        temp_path, original_name = transcribe.save_temp_audio(audio_file)
        
        # Transcribe using Groq Whisper
        api_key = current_app.config.get("GROQ_API_KEY")
        
        # Open the file for Groq (needs a file object with .name attribute)
        with open(temp_path, "rb") as audio_fp:
            text = transcribe.transcribe_audio(audio_fp, api_key=api_key)
        
        return jsonify(text=text)
        
    except transcribe.TranscriptionError as exc:
        return jsonify(error=str(exc)), 400
    except Exception as exc:
        current_app.logger.error(f"Transcription failed: {exc}")
        return jsonify(error="Transcription service unavailable"), 500
    finally:
        if temp_path:
            transcribe.cleanup_temp_file(temp_path)
