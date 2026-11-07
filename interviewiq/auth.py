"""Student registration, login and logout."""
import functools
import re
import sqlite3

from flask import Blueprint, flash, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db, utcnow

bp = Blueprint("auth", __name__)
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
DEPARTMENTS = ["AIML", "CSE", "ISE", "ECE", "EEE", "Mechanical", "Civil", "Other"]


@bp.before_app_request
def load_user():
    uid = session.get("user_id")
    g.user = None
    if uid is not None:
        g.user = get_db().execute("SELECT id, name, email, department FROM users WHERE id = ?", (uid,)).fetchone()
        if g.user is None:
            session.pop("user_id", None)


def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            if request.path.startswith("/api/"):
                return jsonify(error="Please log in."), 401
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)
    return wrapped


def _start_session(user_id: int) -> None:
    session.clear()  # drop any pre-login state (prevents session fixation)
    session["user_id"] = user_id


@bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        department = request.form.get("department", "Other")
        error = None
        if not (2 <= len(name) <= 80):
            error = "Please enter your name (2-80 characters)."
        elif not EMAIL_RE.match(email) or len(email) > 120:
            error = "Please enter a valid email address."
        elif len(password) < 8:
            error = "Password must be at least 8 characters."
        elif department not in DEPARTMENTS:
            department = "Other"
        if error is None:
            try:
                cur = get_db().execute(
                    "INSERT INTO users (name, email, password_hash, department, created_at) VALUES (?, ?, ?, ?, ?)",
                    (name, email, generate_password_hash(password), department, utcnow()),
                )
                get_db().commit()
            except sqlite3.IntegrityError:
                error = "An account with this email already exists."
            else:
                _start_session(cur.lastrowid)
                return redirect(url_for("interview.dashboard"))
        flash(error, "danger")
    return render_template("register.html", departments=DEPARTMENTS)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = get_db().execute("SELECT id, password_hash FROM users WHERE email = ?", (email,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            _start_session(user["id"])
            return redirect(url_for("interview.dashboard"))
        flash("Invalid email or password.", "danger")
    return render_template("login.html")


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
