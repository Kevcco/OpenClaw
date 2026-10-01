import pytest
import time
from types import SimpleNamespace

from app import create_app, db
from app import auth


def seed(app):
    connection = db.connect(app.config["DATABASE_PATH"])
    db.init_schema(connection)
    db.seed_data(connection, app.config["UPLOAD_DIR"])
    connection.close()


def test_token_hash_secret_is_required(tmp_path, monkeypatch):
    monkeypatch.delenv("TOKEN_HASH_SECRET", raising=False)
    with pytest.raises(RuntimeError):
        create_app({"DATABASE_PATH": str(tmp_path / "missing.db")})

    create_app(
        {
            "TESTING": True,
            "TOKEN_HASH_SECRET": "token-secret",
            "DATABASE_PATH": str(tmp_path / "app.db"),
            "UPLOAD_DIR": str(tmp_path / "uploads"),
        }
    )


def test_login_returns_bearer_token_and_wrong_password_does_not(app, client):
    seed(app)
    bad = client.post(
        "/login", json={"username": "teacher_a", "password": "wrong"}
    )
    assert bad.status_code == 401
    assert client.get("/api/me").status_code == 401
    connection = db.connect(app.config["DATABASE_PATH"])
    assert connection.execute("SELECT COUNT(*) FROM auth_tokens").fetchone()[0] == 0
    connection.close()

    response = client.post(
        "/login", json={"username": "teacher_a", "password": "teacher_a_pass"}
    )
    assert response.status_code == 200
    assert response.json["access_token"]
    assert response.json["token_type"] == "Bearer"
    assert response.json["expires_in"] == 28800
    assert response.json["role"] == "teacher"
    assert response.json["class_id"] == 1
    assert not response.headers.getlist("Set-Cookie")
    token = response.json["access_token"]
    assert client.get("/api/me", headers={"Authorization": f"Bearer {token}"}).json["username"] == "teacher_a"
    assert client.post("/login", data={"username": "teacher_a", "password": "teacher_a_pass"}).status_code == 400
    assert client.post("/materials/upload").status_code == 401


def test_logout_invalidates_old_token(app, client):
    seed(app)
    token = client.post("/login", json={"username": "student_a1", "password": "student_a1_pass"}).json["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/me", headers=headers).status_code == 200
    assert client.post("/logout", headers=headers).status_code == 200
    assert client.get("/api/me", headers=headers).status_code == 401


def test_unauthenticated_page_and_api_are_rejected(client):
    page = client.get("/materials")
    assert page.status_code == 200
    page_text = page.get_data(as_text=True)
    assert "A班材料" not in page_text
    assert "B班材料" not in page_text
    api = client.get("/api/me")
    assert api.status_code == 401
    assert "材料" not in api.get_data(as_text=True)


def test_repeated_login_stores_only_digests_and_uses_default_ttl(app, client):
    seed(app)
    first = client.post("/login", json={"username": "teacher_a", "password": "teacher_a_pass"})
    second = client.post("/login", json={"username": "teacher_a", "password": "teacher_a_pass"})
    first_token = first.json["access_token"]
    second_token = second.json["access_token"]
    assert first_token != second_token

    connection = db.connect(app.config["DATABASE_PATH"])
    rows = connection.execute(
        "SELECT token_hash, issued_at, expires_at, revoked_at FROM auth_tokens ORDER BY id"
    ).fetchall()
    connection.close()
    assert len(rows) == 2
    assert all(first_token not in row["token_hash"] and second_token not in row["token_hash"] for row in rows)
    assert all(row["expires_at"] - row["issued_at"] == 28800 for row in rows)
    assert all(row["revoked_at"] is None for row in rows)


def test_expired_unknown_and_malformed_tokens_have_same_401_contract(app, client, monkeypatch):
    seed(app)
    token = client.post(
        "/login", json={"username": "student_a1", "password": "student_a1_pass"}
    ).json["access_token"]
    now = int(time.time())
    monkeypatch.setattr(auth, "time", SimpleNamespace(time=lambda: now + 28800))
    expired = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    unknown = client.get("/api/me", headers={"Authorization": "Bearer unknown-token"})
    malformed = client.get("/api/me", headers={"Authorization": "Basic abc"})
    assert expired.status_code == unknown.status_code == malformed.status_code == 401
    assert expired.json == unknown.json == malformed.json == {"error": "authentication required"}
    assert all(response.headers["WWW-Authenticate"] == "Bearer" for response in (expired, unknown, malformed))
    for path in (
        "/api/materials",
        "/api/knowledge/search?q=一次函数",
    ):
        assert client.get(path, headers={"Authorization": f"Bearer {token}"}).status_code == 401
    assert client.post(
        "/api/ask", headers={"Authorization": f"Bearer {token}"}, json={"question": "一次函数"}
    ).status_code == 401


def test_token_is_not_accepted_from_url_body_cookie_or_other_header(app, client):
    seed(app)
    token = client.post(
        "/login", json={"username": "student_a1", "password": "student_a1_pass"}
    ).json["access_token"]
    assert client.get("/api/me", query_string={"access_token": token}).status_code == 401
    assert client.post("/api/ask", json={"access_token": token, "question": "一次函数"}).status_code == 401
    assert client.get("/api/me", headers={"X-Access-Token": token}).status_code == 401
    assert client.get("/api/me", headers={"Cookie": f"access_token={token}"}).status_code == 401
    assert client.get("/api/me", headers={"Authorization": f"Bearer {token} extra"}).status_code == 401
