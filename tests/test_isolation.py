from app import db


def seed(app):
    connection = db.connect(app.config["DATABASE_PATH"])
    db.init_schema(connection)
    db.seed_data(connection, app.config["UPLOAD_DIR"])
    connection.close()


def login(client, username, password):
    response = client.post("/login", json={"username": username, "password": password})
    assert response.status_code == 200


def test_lists_are_filtered_by_session_class(app, client):
    seed(app)
    login(client, "student_a1", "student_a1_pass")
    response = client.get("/api/materials")
    assert response.status_code == 200
    titles = [item["title"] for item in response.json["materials"]]
    assert any("A班" in title for title in titles)
    assert all("B班" not in title for title in titles)

    login(client, "student_b1", "student_b1_pass")
    response = client.get("/api/materials")
    titles = [item["title"] for item in response.json["materials"]]
    assert any("B班" in title for title in titles)
    assert all("A班" not in title for title in titles)


def test_cross_class_id_returns_404_without_leaking_material(app, client):
    seed(app)
    login(client, "teacher_a", "teacher_a_pass")
    response = client.get("/api/materials/2")
    assert response.status_code == 404
    assert "B班" not in response.get_data(as_text=True)


def test_client_class_id_cannot_override_session(app, client):
    seed(app)
    login(client, "teacher_a", "teacher_a_pass")
    response = client.get("/api/materials?class_id=2")
    assert response.status_code == 200
    assert all(item["class_id"] == 1 for item in response.json["materials"])
    response = client.patch(
        "/api/materials/2?class_id=2",
        json={"class_id": 2, "title": "越权改名"},
    )
    assert response.status_code == 404


def test_search_and_page_use_same_class_filter(app, client):
    seed(app)
    login(client, "student_a1", "student_a1_pass")
    response = client.get("/api/materials?q=数学")
    assert response.status_code == 200
    assert all(item["class_id"] == 1 for item in response.json["materials"])
    page = client.get("/materials")
    assert page.status_code == 200
    assert "A班材料" in page.get_data(as_text=True)
    assert "B班材料" not in page.get_data(as_text=True)
