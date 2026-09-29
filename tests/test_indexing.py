import pathlib

from app import db
from app.indexing import rebuild_material
from app.vector_store import HashEmbeddingProvider, InMemoryVectorStore


def initialize(tmp_path):
    database_path = pathlib.Path(tmp_path) / "app.db"
    upload_dir = pathlib.Path(tmp_path) / "uploads"
    connection = db.connect(database_path)
    db.init_schema(connection)
    db.seed_data(connection, upload_dir)
    return connection


def test_rebuild_is_idempotent_and_vectors_use_chunk_ids(tmp_path):
    connection = initialize(tmp_path)
    store = InMemoryVectorStore()
    result = rebuild_material(
        connection,
        1,
        embedding_provider=HashEmbeddingProvider(),
        vector_store=store,
    )
    first = db.list_knowledge_chunks(1, connection=connection)
    assert result["vector_status"] == "ready"
    assert first
    assert all(point_id == chunk["id"] for point_id, (_vector, _payload) in store.points.items() for chunk in first if point_id == chunk["id"])
    rebuild_material(
        connection,
        1,
        embedding_provider=HashEmbeddingProvider(),
        vector_store=store,
    )
    second = db.list_knowledge_chunks(1, connection=connection)
    assert len(second) == len(first)
    assert len(store.points) == len(second)
    connection.close()


def test_embedding_failure_keeps_ready_keyword_chunks_and_records_vector_failure(tmp_path):
    connection = initialize(tmp_path)

    class BrokenProvider:
        def embed(self, _texts):
            raise RuntimeError("gateway down")

    result = rebuild_material(
        connection,
        1,
        embedding_provider=BrokenProvider(),
        vector_store=InMemoryVectorStore(),
    )
    chunks = db.list_knowledge_chunks(1, connection=connection)
    assert result["vector_status"] == "failed"
    assert chunks and all(chunk["index_status"] == "ready" for chunk in chunks)
    assert all(chunk["vector_status"] == "failed" for chunk in chunks)
    assert all(chunk["index_error"] == "gateway down" for chunk in chunks)
    connection.close()
