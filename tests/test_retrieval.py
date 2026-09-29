import pathlib

from app import db
from app.indexing import rebuild_material
from app.retrieval import NOT_FOUND_MESSAGE, RetrievalUnavailable, search
from app.vector_store import HashEmbeddingProvider, InMemoryVectorStore


def initialize(tmp_path):
    connection = db.connect(pathlib.Path(tmp_path) / "app.db")
    db.init_schema(connection)
    db.seed_data(connection, pathlib.Path(tmp_path) / "uploads")
    store = InMemoryVectorStore()
    provider = HashEmbeddingProvider()
    rebuild_material(connection, 1, embedding_provider=provider, vector_store=store)
    rebuild_material(connection, 2, embedding_provider=provider, vector_store=store)
    return connection, provider, store


def test_keyword_retrieval_is_class_scoped(tmp_path):
    connection, provider, store = initialize(tmp_path)
    result = search(connection, 1, "一次函数", mode="keyword", embedding_provider=provider, vector_store=store)
    assert result["hits"]
    assert all(row["class_id"] == 1 for row, _score, _modes in result["hits"])
    missing = search(connection, 1, "几何图形", mode="keyword", embedding_provider=provider, vector_store=store)
    assert missing["hits"] == []
    assert missing["message"] == NOT_FOUND_MESSAGE
    connection.close()


def test_vector_and_hybrid_retrieval_return_traceable_rows(tmp_path):
    connection, provider, store = initialize(tmp_path)
    vector = search(connection, 1, "一次函数", mode="vector", embedding_provider=provider, vector_store=store)
    hybrid = search(connection, 1, "一次函数", mode="hybrid", embedding_provider=provider, vector_store=store)
    assert vector["hits"]
    assert hybrid["hits"]
    row, score, modes = hybrid["hits"][0]
    assert row["material_id"] == 1
    assert row["chunk_text"] in "A班材料正文：一次函数基础。"
    assert score > 0
    assert modes == {"keyword", "vector"}
    connection.close()


def test_vector_retrieval_requires_available_dependencies(tmp_path):
    connection, _provider, _store = initialize(tmp_path)
    try:
        search(connection, 1, "一次函数", mode="vector")
    except RetrievalUnavailable:
        pass
    else:
        raise AssertionError("vector retrieval should fail when dependencies are absent")
    connection.close()
