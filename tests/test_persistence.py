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
        "SECRET_KEY": "persistence-test-key",
        "DATABASE_PATH": str(tmp_path / "data" / "app.db"),
        "UPLOAD_DIR": str(tmp_path / "uploads"),
    }
    first_app = create_app(config)
    initialize(first_app)
    first_client = first_app.test_client()
    first_client.post("/login", json={"username": "teacher_a", "password": "teacher_a_pass"})
    upload = first_client.post(
        "/api/materials/upload",
        data={"file": (io.BytesIO(b"persistent body"), "persistent.md")},
        content_type="multipart/form-data",
    )
    assert upload.status_code == 201

    second_app = create_app(config)
    initialize(second_app)
    second_client = second_app.test_client()
    assert second_client.post(
        "/login", json={"username": "teacher_a", "password": "teacher_a_pass"}
    ).status_code == 200
    titles = [item["title"] for item in second_client.get("/api/materials").json["materials"]]
    assert "persistent" in titles
