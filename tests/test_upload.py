import io
import sqlite3

from app import db
from app import knowledge
from app import materials as materials_routes


def seed(app):
    connection = db.connect(app.config["DATABASE_PATH"])
    db.init_schema(connection)
    db.seed_data(connection, app.config["UPLOAD_DIR"])
    connection.close()


def login(client, username, password):
    response = client.post("/login", json={"username": username, "password": password})
    assert response.status_code == 200


def counts(app):
    connection = sqlite3.connect(app.config["DATABASE_PATH"])
    try:
        return {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("materials", "knowledge_entries")
        }
    finally:
        connection.close()


def test_student_upload_is_rejected_before_side_effects(app, client):
    seed(app)
    login(client, "student_a1", "student_a1_pass")
    before = counts(app)
    response = client.post(
        "/api/materials/upload",
        data={"file": (io.BytesIO(b"student content"), "student.md")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 403
    assert counts(app) == before
    assert not list((__import__("pathlib").Path(app.config["UPLOAD_DIR"])).glob("**/*.part"))


def test_teacher_upload_writes_both_tables_and_is_visible_to_same_class(app, client):
    seed(app)
    login(client, "teacher_a", "teacher_a_pass")
    before = counts(app)
    response = client.post(
        "/api/materials/upload",
        data={
            "title": "A班新增材料",
            "file": (io.BytesIO(b"# A class body\ncontent"), "lesson.md"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 201
    assert counts(app) == {"materials": before["materials"] + 1, "knowledge_entries": before["knowledge_entries"] + 1}
    material_id = response.json["material_id"]
    detail = client.get(f"/api/materials/{material_id}")
    assert detail.status_code == 200
    assert detail.json["body_text"].startswith("# A class body")
    assert any(
        item["title"] == "A班新增材料"
        for item in client.get("/api/materials").json["materials"]
    )

    login(client, "student_a1", "student_a1_pass")
    assert any(item["title"] == "A班新增材料" for item in client.get("/api/materials").json["materials"])
    login(client, "student_b1", "student_b1_pass")
    assert all(item["title"] != "A班新增材料" for item in client.get("/api/materials").json["materials"])


def test_upload_validation_leaves_no_database_or_disk_side_effects(app, client):
    seed(app)
    login(client, "teacher_a", "teacher_a_pass")
    before = counts(app)
    upload_root = __import__("pathlib").Path(app.config["UPLOAD_DIR"])
    for filename, content in (("bad.exe", b"content"), ("empty.md", b""), ("bad.md", b"\xff\xfe")):
        response = client.post(
            "/api/materials/upload",
            data={"file": (io.BytesIO(content), filename)},
            content_type="multipart/form-data",
        )
        assert response.status_code == 400
        assert counts(app) == before
        assert not list(upload_root.glob("**/*.part"))

    app.config["MAX_UPLOAD_BYTES"] = 4
    response = client.post(
        "/api/materials/upload",
        data={"file": (io.BytesIO(b"12345"), "large.md")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 400
    assert counts(app) == before


def test_database_failure_rolls_back_and_cleans_temp_file(app, client, monkeypatch):
    seed(app)
    login(client, "teacher_a", "teacher_a_pass")
    before = counts(app)

    def fail_persist(*_args, **_kwargs):
        raise sqlite3.OperationalError("simulated database failure")

    monkeypatch.setattr(knowledge, "persist_material", fail_persist)
    response = client.post(
        "/api/materials/upload",
        data={"file": (io.BytesIO(b"content"), "db-failure.md")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 500
    assert counts(app) == before
    assert not list(__import__("pathlib").Path(app.config["UPLOAD_DIR"]).glob("**/*.part"))


def test_final_move_failure_rolls_back_and_cleans_files(app, client, monkeypatch):
    seed(app)
    login(client, "teacher_a", "teacher_a_pass")
    before = counts(app)

    def fail_replace(*_args, **_kwargs):
        raise OSError("simulated move failure")

    monkeypatch.setattr(materials_routes.os, "replace", fail_replace)
    response = client.post(
        "/api/materials/upload",
        data={"file": (io.BytesIO(b"content"), "move-failure.md")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 500
    assert counts(app) == before
    upload_root = __import__("pathlib").Path(app.config["UPLOAD_DIR"])
    assert not list(upload_root.glob("**/*.part"))
    assert not list(upload_root.glob("**/*move-failure.md"))
