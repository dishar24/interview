"""InterviewIQ AI: voice-based mock interview platform (Flask)."""
import hmac
import json
import logging
import os
import secrets

from flask import Flask, abort, jsonify, render_template, request, session

from . import db
from .evaluator import make_evaluator


def _load_secret_key(instance_path: str) -> str:
    """SECRET_KEY from env, else a key persisted in the instance folder (so dev restarts keep sessions)."""
    env_key = os.environ.get("SECRET_KEY")
    if env_key:
        return env_key
    path = os.path.join(instance_path, ".secret_key")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read().strip()
    key = secrets.token_hex(32)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(key)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return key


def create_app(test_config: dict | None = None) -> Flask:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    logging.basicConfig(level=logging.INFO)
    app = Flask(__name__, instance_relative_config=True)
    os.makedirs(app.instance_path, exist_ok=True)

    app.config.from_mapping(
        SECRET_KEY=_load_secret_key(app.instance_path),
        DATABASE=os.path.join(app.instance_path, "interviewiq.db"),
        GROQ_API_KEY=os.environ.get("GROQ_API_KEY"),
        EVAL_MODEL=os.environ.get("EVAL_MODEL", "openai/gpt-oss-120b"),
        MAX_TRANSCRIPT_CHARS=4000,
        MAX_CONTENT_LENGTH=26 * 1024 * 1024,  # 26 MB (allows Whisper audio up to 25 MB)
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE") == "1",
    )
    if test_config:
        app.config.update(test_config)

    db.init_app(app)
    app.extensions["evaluator"] = make_evaluator(app.config)

    # ---- CSRF protection (session token; sent as form field or X-CSRF-Token header)
    def csrf_token() -> str:
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_hex(16)
        return session["csrf_token"]

    app.jinja_env.globals["csrf_token"] = csrf_token
    app.jinja_env.filters["fromjson"] = lambda s: json.loads(s) if s else []

    @app.before_request
    def csrf_protect():
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token") or ""
            expected = session.get("csrf_token", "")
            if not expected or not hmac.compare_digest(sent, expected):
                abort(400, description="Invalid or missing CSRF token.")

    from . import auth, interview
    app.register_blueprint(auth.bp)
    app.register_blueprint(interview.bp)

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        # microphone is needed for speech recognition; everything else is off
        resp.headers.setdefault("Permissions-Policy", "microphone=(self), camera=(), geolocation=()")
        return resp

    def wants_json() -> bool:
        return request.path.startswith("/api/")

    @app.errorhandler(400)
    @app.errorhandler(404)
    @app.errorhandler(413)
    def handle_client_error(err):
        if wants_json():
            return jsonify(error=getattr(err, "description", "Bad request")), err.code
        return render_template("error.html", code=err.code, message=getattr(err, "description", "")), err.code

    @app.errorhandler(500)
    def handle_server_error(err):
        if wants_json():
            return jsonify(error="Something went wrong on our side."), 500
        return render_template("error.html", code=500, message="Something went wrong on our side."), 500

    return app
