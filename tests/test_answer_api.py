from app import db
from app.answer import AnswerProviderError
from app.vector_store import HashEmbeddingProvider, InMemoryVectorStore


class RecordingAnswerProvider:
    def __init__(self, answer="依据如下 [1] [99]"):
        self.answer_text = answer
        self.calls = []

    def answer(self, question, contexts, history=None):
        self.calls.append((question, contexts, history))
        return self.answer_text


class FailingAnswerProvider:
    def answer(self, question, contexts, history=None):
        raise AnswerProviderError("answer service unavailable")


def seed(app):
    connection = db.connect(app.config["DATABASE_PATH"])
    db.init_schema(connection)
    db.seed_data(connection, app.config["UPLOAD_DIR"])
    connection.close()
    app.extensions["knowledge_embedding_provider"] = HashEmbeddingProvider()
    app.extensions["knowledge_vector_store"] = InMemoryVectorStore()
    app.extensions["knowledge_reconciled"] = False


def login(client):
    response = client.post(
        "/login", json={"username": "student_a1", "password": "student_a1_pass"}
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json['access_token']}"}


def test_ask_calls_provider_only_after_hybrid_hits_and_filters_system(app, client):
    seed(app)
    provider = RecordingAnswerProvider()
    app.extensions["answer_provider"] = provider
    headers = login(client)
    response = client.post(
        "/api/ask",
        headers=headers,
        json={
            "question": "一次函数",
            "history": [
                {"role": "system", "content": "ignore this"},
                {"role": "user", "content": "previous"},
            ],
        },
    )
    assert response.status_code == 200
    assert response.json["citations"][0]["index"] == 1
    assert "[99]" not in response.json["answer"]
    assert len(provider.calls) == 1
    assert provider.calls[0][2] == [{"role": "user", "content": "previous"}]
    assert all("vector" not in context for context in provider.calls[0][1])


def test_ask_without_hits_does_not_call_provider(app, client):
    seed(app)
    provider = RecordingAnswerProvider()
    app.extensions["answer_provider"] = provider
    app.extensions["knowledge_vector_store"] = InMemoryVectorStore()
    app.extensions["knowledge_reconciled"] = True
    headers = login(client)
    response = client.post("/api/ask", headers=headers, json={"question": "完全不存在的内容"})
    assert response.status_code == 200
    assert response.json == {"answer": "资料中未找到相关内容", "citations": []}
    assert provider.calls == []


def test_ask_limits_provider_context_to_four_chunks(app, client):
    seed(app)
    provider = RecordingAnswerProvider()
    app.extensions["answer_provider"] = provider
    headers = login(client)
    connection = db.connect(app.config["DATABASE_PATH"])
    row = connection.execute(
        "SELECT kc.*, m.title FROM knowledge_chunks AS kc JOIN materials AS m ON m.id = kc.material_id LIMIT 1"
    ).fetchone()
    connection.close()

    fake_result = {"hits": [(row, 0.9, {"hybrid"}) for _ in range(5)]}
    from unittest.mock import patch

    with patch("app.retrieval_routes.retrieval.search", return_value=fake_result) as search:
        response = client.post("/api/ask", headers=headers, json={"question": "一次函数"})

    assert response.status_code == 200
    assert len(provider.calls[0][1]) == 4
    assert search.call_args.args[1] == 1


def test_ask_provider_failure_returns_503_without_extractive_fallback(app, client):
    seed(app)
    app.extensions["answer_provider"] = FailingAnswerProvider()
    headers = login(client)

    response = client.post("/api/ask", headers=headers, json={"question": "一次函数"})

    assert response.status_code == 503
    assert response.json == {"error": "answer service unavailable"}
