from app import db
from app.vector_store import HashEmbeddingProvider, InMemoryVectorStore


class RecordingAnswerProvider:
    def __init__(self, answer="依据如下 [1] [99]"):
        self.answer_text = answer
        self.calls = []

    def answer(self, question, contexts, history=None):
        self.calls.append((question, contexts, history))
        return self.answer_text


def seed(app):
    connection = db.connect(app.config["DATABASE_PATH"])
    db.init_schema(connection)
    db.seed_data(connection, app.config["UPLOAD_DIR"])
    connection.close()
    app.extensions["knowledge_embedding_provider"] = HashEmbeddingProvider()
    app.extensions["knowledge_vector_store"] = InMemoryVectorStore()
    app.extensions["knowledge_reconciled"] = False


def login(client):
    assert client.post(
        "/login", json={"username": "student_a1", "password": "student_a1_pass"}
    ).status_code == 200


def test_ask_calls_provider_only_after_hybrid_hits_and_filters_system(app, client):
    seed(app)
    provider = RecordingAnswerProvider()
    app.extensions["answer_provider"] = provider
    login(client)
    response = client.post(
        "/api/ask",
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
    login(client)
    response = client.post("/api/ask", json={"question": "完全不存在的内容"})
    assert response.status_code == 200
    assert response.json == {"answer": "资料中未找到相关内容", "citations": []}
    assert provider.calls == []
