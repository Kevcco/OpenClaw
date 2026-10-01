import hashlib
import hmac
import secrets
import sqlite3
import time
from functools import wraps

import bcrypt
from flask import (
    Blueprint,
    current_app,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from . import db


bp = Blueprint("auth", __name__)


def is_api_request():
    """Return whether the request expects the JSON authentication contract."""

    return (
        request.path.startswith("/api/")
        or request.path in {"/login", "/logout", "/materials/upload"}
        or request.is_json
    )


def unauthorized_response():
    if is_api_request():
        return (
            jsonify({"error": "authentication required"}),
            401,
            {"WWW-Authenticate": "Bearer"},
        )
    return redirect(url_for("auth.login"))


def _token_hash(token):
    secret = current_app.config.get("TOKEN_HASH_SECRET")
    if not secret:
        raise RuntimeError("TOKEN_HASH_SECRET must be provided by the environment")
    if isinstance(secret, str):
        secret = secret.encode("utf-8")
    return hmac.new(secret, token.encode("utf-8"), hashlib.sha256).hexdigest()


def issue_access_token(user_id):
    """Create and persist a random opaque access token.

    The returned raw value is deliberately never written to the database. Only
    its HMAC digest is persisted, so a database read cannot be used directly as
    an Authorization credential.
    """

    ttl = int(current_app.config["ACCESS_TOKEN_TTL_SECONDS"])
    issued_at = int(time.time())
    expires_at = issued_at + ttl
    connection = db.get_db()
    for _ in range(3):
        token = secrets.token_urlsafe(48)
        digest = _token_hash(token)
        try:
            connection.execute(
                """
                INSERT INTO auth_tokens (token_hash, user_id, issued_at, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                (digest, user_id, issued_at, expires_at),
            )
            connection.commit()
            return token, issued_at, expires_at
        except sqlite3.IntegrityError:
            connection.rollback()
    raise RuntimeError("could not issue access token")


def parse_bearer_token():
    """Read exactly one opaque token from the Authorization header.

    Cookies, query parameters, request bodies, and all other headers are
    intentionally ignored. The token alphabet matches ``secrets.token_urlsafe``
    and disallows embedded whitespace or additional Authorization fields.
    """

    header = request.headers.get("Authorization", "")
    parts = header.strip().split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1]
    if not token or any(character.isspace() for character in token):
        return None
    return token


def _auth_record():
    if hasattr(g, "auth_record"):
        return g.auth_record

    token = parse_bearer_token()
    if token is None:
        g.auth_record = None
        return None

    now = int(time.time())
    digest = _token_hash(token)
    g.auth_record = db.get_db().execute(
        """
        SELECT
            auth_tokens.id AS token_id,
            auth_tokens.issued_at,
            auth_tokens.expires_at,
            users.id,
            users.username,
            users.role,
            users.class_id
        FROM auth_tokens
        JOIN users ON users.id = auth_tokens.user_id
        WHERE auth_tokens.token_hash = ?
          AND auth_tokens.revoked_at IS NULL
          AND auth_tokens.expires_at > ?
        """,
        (digest, now),
    ).fetchone()
    return g.auth_record


def current_user():
    return _auth_record()


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


def _user_payload(user):
    return {
        "user_id": user["id"],
        "username": user["username"],
        "role": user["role"],
        "class_id": user["class_id"],
    }


@bp.route("/login", methods=("GET", "POST"))
def login():
    if request.method == "GET":
        return render_template("login.html")

    if not request.is_json:
        return jsonify({"error": "JSON credentials are required"}), 400

    payload = request.get_json(silent=True)
    payload = payload or {}
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
        return jsonify({"error": "invalid credentials"}), 401

    token, _issued_at, expires_at = issue_access_token(user["id"])
    response = {
        "access_token": token,
        "token_type": "Bearer",
        "expires_in": int(current_app.config["ACCESS_TOKEN_TTL_SECONDS"]),
        "expires_at": expires_at,
        **_user_payload(user),
    }
    return jsonify(response)


@bp.route("/logout", methods=("POST",))
@bp.route("/api/logout", methods=("POST",))
@login_required
def logout():
    record = current_user()
    db.get_db().execute(
        "UPDATE auth_tokens SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
        (int(time.time()), record["token_id"]),
    )
    db.get_db().commit()
    return jsonify({"status": "ok"})


@bp.route("/api/me")
@login_required
def me():
    return jsonify(_user_payload(current_user()))
