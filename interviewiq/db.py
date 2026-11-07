"""SQLite helpers: connection per request, schema creation and question seeding."""
import json
import sqlite3
from datetime import datetime, timezone
from importlib import resources

import click
from flask import current_app, g

QUESTIONS_FILE = "data/questions.json"
DEFAULT_CRITERIA = "Accurate definition, coverage of the key concepts, and a concrete example."


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_exc=None) -> None:
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def load_question_file() -> list[dict]:
    with resources.files("interviewiq").joinpath(QUESTIONS_FILE).open("r", encoding="utf-8") as fh:
        return json.load(fh)


def seed_questions(conn: sqlite3.Connection) -> int:
    """Insert any questions from questions.json that are not already in the DB (matched by text)."""
    added = 0
    for q in load_question_file():
        cur = conn.execute(
            """INSERT OR IGNORE INTO questions
               (text, subject, topic, difficulty, category, expected_concepts, reference_answer, evaluation_criteria)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                q["text"], q["subject"], q.get("topic"), q["difficulty"], q["category"],
                json.dumps(q["expected_concepts"]), q["reference_answer"],
                q.get("evaluation_criteria") or DEFAULT_CRITERIA,
            ),
        )
        added += cur.rowcount
    conn.commit()
    return added


def init_db(app=None) -> None:
    app = app or current_app
    schema = resources.files("interviewiq").joinpath("schema.sql").read_text(encoding="utf-8")
    conn = sqlite3.connect(app.config["DATABASE"])
    try:
        conn.executescript(schema)
        seed_questions(conn)
    finally:
        conn.close()


def init_app(app) -> None:
    app.teardown_appcontext(close_db)
    with app.app_context():
        init_db(app)

    @app.cli.command("seed-questions")
    def seed_cmd():
        """Add new questions from data/questions.json to the database."""
        conn = sqlite3.connect(app.config["DATABASE"])
        try:
            click.echo(f"Added {seed_questions(conn)} new question(s).")
        finally:
            conn.close()
