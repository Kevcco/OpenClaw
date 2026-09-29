import pathlib

from app import db
from app.indexing import rebuild_material
from app.vector_store import InMemoryVectorStore


def initialize(tmp_path):
    connection = db.connect(pathlib.Path(tmp_path) / "app.db")
    db.init_schema(connection)
    db.seed_data(connection, pathlib.Path(tmp_path) / "uploads")
    return connection


def test_vector_payload_contains_identifiers_but_not_chunk_text(tmp_path):
    connection = initialize(tmp_path)

    class Provider:
        def embed(self, texts):
            return [[1.0, 0.0] for _ in texts]

    store = InMemoryVectorStore()
    rebuild_material(connection, 1, embedding_provider=Provider(), vector_store=store)
    assert store.points
    for _point_id, (_vector, payload) in store.points.items():
        assert "chunk_id" in payload
        assert "class_id" in payload
        assert "chunk_text" not in payload
    connection.close()


def test_vector_dimension_mismatch_is_recorded(tmp_path):
    connection = initialize(tmp_path)
    connection.execute(
        "UPDATE knowledge_entries SET body_text = ? WHERE material_id = 1",
        ("长文本。" * 300,),
    )
    connection.commit()

    class Provider:
        def embed(self, texts):
            return [[1.0], [1.0, 0.0]][: len(texts)]

    result = rebuild_material(
        connection,
        1,
        embedding_provider=Provider(),
        vector_store=InMemoryVectorStore(),
    )
    assert result["vector_status"] == "failed"
    assert "dimensions" in result["error"]
    connection.close()
