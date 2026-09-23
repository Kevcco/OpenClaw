def login(client, username, password):
    response = client.post("/login", json={"username": username, "password": password})
    assert response.status_code == 200


def test_workspace_loads_assets_and_uses_server_identity(client, app):
    from app import db

    connection = db.connect(app.config["DATABASE_PATH"])
    db.init_schema(connection)
    db.seed_data(connection, app.config["UPLOAD_DIR"])
    connection.close()
    login(client, "teacher_a", "teacher_a_pass")

    page = client.get("/materials")
    script = client.get("/static/workspace.js")
    stylesheet = client.get("/static/app.css")

    assert page.status_code == 200
    assert b"data-upload-panel" in page.data
    assert b"/api/me" in script.data
    assert b"/api/materials/upload" in script.data
    assert b"/api/materials" in script.data
    assert b"textContent = material.body_text" in script.data
    assert stylesheet.status_code == 200


def test_student_cannot_use_upload_even_with_workspace_script(client, app):
    from app import db

    connection = db.connect(app.config["DATABASE_PATH"])
    db.init_schema(connection)
    db.seed_data(connection, app.config["UPLOAD_DIR"])
    connection.close()
    login(client, "student_a1", "student_a1_pass")

    assert client.get("/api/me").json["role"] == "student"
    assert client.post("/api/materials/upload").status_code == 403

