from functools import wraps

import bcrypt
from flask import (
    Blueprint,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from . import db


bp = Blueprint("auth", __name__)


def is_api_request():
    return request.path.startswith("/api/") or request.is_json


def unauthorized_response():
    if is_api_request():
        return jsonify({"error": "authentication required"}), 401
    return redirect(url_for("auth.login"))


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    user = db.get_db().execute(
        "SELECT id, username, role, class_id FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    if user is None:
        session.clear()
    return user


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_user() is None:
            return unauthorized_response()
        return view(*args, **kwargs)

    return wrapped


def role_required(role):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = current_user()
            if user is None:
                return unauthorized_response()
            if user["role"] != role:
                return jsonify({"error": "forbidden"}), 403
            return view(*args, **kwargs)

        return wrapped

    return decorator


@bp.route("/login", methods=("GET", "POST"))
def login():
    if request.method == "GET":
        return render_template("login.html")

    payload = request.get_json(silent=True) if request.is_json else request.form
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""
    user = db.get_db().execute(
        "SELECT id, username, password_hash, role, class_id FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    valid = user is not None and bcrypt.checkpw(
        password.encode("utf-8"), user["password_hash"].encode("ascii")
    )
    if not valid:
        if is_api_request():
            return jsonify({"error": "invalid credentials"}), 401
        return render_template("login.html", error="账号或密码错误"), 401

    session.clear()
    session.update(
        user_id=user["id"], role=user["role"], class_id=user["class_id"]
    )
    if is_api_request():
        return jsonify(
            {
                "user_id": user["id"],
                "username": user["username"],
                "role": user["role"],
                "class_id": user["class_id"],
            }
        )
    return redirect(url_for("materials.materials_page"))


@bp.route("/logout", methods=("GET", "POST"))
def logout():
    session.clear()
    if is_api_request():
        return jsonify({"status": "ok"})
    return redirect(url_for("auth.login"))


@bp.route("/api/me")
@login_required
def me():
    user = current_user()
    return jsonify(
        {
            "user_id": user["id"],
            "username": user["username"],
            "role": user["role"],
            "class_id": user["class_id"],
        }
    )
