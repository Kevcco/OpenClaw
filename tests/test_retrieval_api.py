from app import db
from app.vector_store import HashEmbeddingProvider, InMemoryVectorStore


def seed(app):
    connection = db.connect(app.config["DATABASE_PATH"])
    db.init_schema(connection)
    db.seed_data(connection, app.config["UPLOAD_DIR"])
    connection.close()
    app.extensions["knowledge_embedding_provider"] = HashEmbeddingProvider()
    app.extensions["knowledge_vector_store"] = InMemoryVectorStore()
    app.extensions["knowledge_reconciled"] = False


def login(client, username, password):
    response = client.post("/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json['access_token']}"}


def test_search_api_returns_traceable_class_scoped_hits(app, client):
    seed(app)
    headers = login(client, "student_a1", "student_a1_pass")
    response = client.get("/api/knowledge/search?q=一次函数&mode=keyword", headers=headers)
    assert response.status_code == 200
    assert response.json["hits"]
    hit = response.json["hits"][0]
    assert hit["source"]["title"].startswith("A班")
    assert hit["source"]["preview_url"].startswith("/api/materials/")
    assert "B班" not in response.get_data(as_text=True)

    response = client.get("/api/knowledge/search?q=几何图形&class_id=2", headers=headers)
    assert response.status_code == 200
    assert response.json["hits"] == []
    assert response.json["message"] == "资料中未找到相关内容"


def test_search_api_validates_auth_input_and_vector_modes(app, client):
    seed(app)
    assert client.get("/api/knowledge/search?q=一次函数").status_code == 401
    headers = login(client, "student_a1", "student_a1_pass")
    assert client.get("/api/knowledge/search?q=%20%20", headers=headers).status_code == 400
    response = client.get("/api/knowledge/search?q=一次函数&mode=vector&limit=1", headers=headers)
    assert response.status_code == 200
    assert len(response.json["hits"]) <= 1
