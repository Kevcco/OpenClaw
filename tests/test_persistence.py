import io
from pathlib import Path

from app import create_app, db


def initialize(app):
    Path(app.config["DATABASE_PATH"]).parent.mkdir(parents=True, exist_ok=True)
    connection = db.connect(app.config["DATABASE_PATH"])
    db.init_schema(connection)
    db.seed_data(connection, app.config["UPLOAD_DIR"])
    connection.close()


def test_seed_and_upload_survive_application_restart(tmp_path):
    config = {
        "TESTING": True,
        "TOKEN_HASH_SECRET": "persistence-token-secret",
        "ACCESS_TOKEN_TTL_SECONDS": 28800,
        "DATABASE_PATH": str(tmp_path / "data" / "app.db"),
        "UPLOAD_DIR": str(tmp_path / "uploads"),
    }
    first_app = create_app(config)
    initialize(first_app)
    first_client = first_app.test_client()
    token = first_client.post("/login", json={"username": "teacher_a", "password": "teacher_a_pass"}).json["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    upload = first_client.post(
        "/api/materials/upload",
        headers=headers,
        data={"file": (io.BytesIO(b"persistent body"), "persistent.md")},
        content_type="multipart/form-data",
    )
    assert upload.status_code == 201

    second_app = create_app(config)
    initialize(second_app)
    second_client = second_app.test_client()
    token = second_client.post(
        "/login", json={"username": "teacher_a", "password": "teacher_a_pass"}
    ).json["access_token"]
    titles = [item["title"] for item in second_client.get("/api/materials", headers={"Authorization": f"Bearer {token}"}).json["materials"]]
    assert "persistent" in titles


def test_schema_migration_is_idempotent_and_preserves_tokens_and_knowledge(tmp_path):
    config = {
        "TESTING": True,
        "TOKEN_HASH_SECRET": "migration-token-secret",
        "DATABASE_PATH": str(tmp_path / "data" / "app.db"),
        "UPLOAD_DIR": str(tmp_path / "uploads"),
    }
    app = create_app(config)
    initialize(app)
    client = app.test_client()
    token = client.post(
        "/login", json={"username": "student_a1", "password": "student_a1_pass"}
    ).json["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    before = client.get("/api/materials", headers=headers).json["materials"]
    connection = db.connect(app.config["DATABASE_PATH"])
    before_knowledge = connection.execute("SELECT COUNT(*) FROM knowledge_entries").fetchone()[0]
    before_chunks = connection.execute("SELECT COUNT(*) FROM knowledge_chunks").fetchone()[0]
    connection.close()

    initialize(app)

    after = client.get("/api/materials", headers=headers)
    assert after.status_code == 200
    assert after.json["materials"] == before
    connection = db.connect(app.config["DATABASE_PATH"])
    assert connection.execute("SELECT COUNT(*) FROM auth_tokens").fetchone()[0] == 1
    assert connection.execute("SELECT COUNT(*) FROM knowledge_entries").fetchone()[0] == before_knowledge
    assert connection.execute("SELECT COUNT(*) FROM knowledge_chunks").fetchone()[0] == before_chunks
    connection.close()
