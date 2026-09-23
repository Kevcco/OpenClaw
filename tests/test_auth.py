import pytest

from app import create_app, db


def seed(app):
    connection = db.connect(app.config["DATABASE_PATH"])
    db.init_schema(connection)
    db.seed_data(connection, app.config["UPLOAD_DIR"])
    connection.close()


def test_secret_key_is_required_and_cookie_settings_are_secure(tmp_path, monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError):
        create_app({"DATABASE_PATH": str(tmp_path / "missing.db")})

    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "secret",
            "DATABASE_PATH": str(tmp_path / "app.db"),
            "UPLOAD_DIR": str(tmp_path / "uploads"),
        }
    )
    assert app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"


def test_login_sets_session_fields_and_wrong_password_does_not(app, client):
    seed(app)
    bad = client.post(
        "/login", json={"username": "teacher_a", "password": "wrong"}
    )
    assert bad.status_code == 401
    assert client.get("/api/me").status_code == 401

    response = client.post(
        "/login", json={"username": "teacher_a", "password": "teacher_a_pass"}
    )
    assert response.status_code == 200
    assert response.json["role"] == "teacher"
    assert response.json["class_id"] == 1
    assert client.get("/api/me").json["username"] == "teacher_a"


def test_logout_invalidates_old_session(app, client):
    seed(app)
    client.post("/login", json={"username": "student_a1", "password": "student_a1_pass"})
    assert client.get("/api/me").status_code == 200
    assert client.post("/logout", json={}).status_code == 200
    assert client.get("/api/me").status_code == 401


def test_unauthenticated_page_and_api_are_rejected(client):
    page = client.get("/materials")
    assert page.status_code == 302
    assert page.headers["Location"].endswith("/login")
    api = client.get("/api/me")
    assert api.status_code == 401
    assert "材料" not in api.get_data(as_text=True)
