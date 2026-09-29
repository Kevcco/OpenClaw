"""Material-to-chunk indexing and recoverable vector synchronization."""

from __future__ import annotations

import hashlib

from . import chunking, db
from .vector_store import EmbeddingProviderError, VectorStoreError, VectorStoreUnavailable


class IndexingError(RuntimeError):
    pass


def _material_row(connection, material_id):
    return connection.execute(
        """
        SELECT materials.id, materials.class_id, knowledge_entries.id AS knowledge_entry_id,
               knowledge_entries.body_text
        FROM materials
        JOIN knowledge_entries ON knowledge_entries.material_id = materials.id
        WHERE materials.id = ?
        """,
        (material_id,),
    ).fetchone()


def _vector_payload(row, chunk_id, chunk_index):
    return {
        "class_id": row["class_id"],
        "material_id": row["id"],
        "knowledge_entry_id": row["knowledge_entry_id"],
        "chunk_id": chunk_id,
        "chunk_index": chunk_index,
    }


def rebuild_material(
    connection,
    material_id,
    *,
    strategy="auto",
    max_chars=chunking.DEFAULT_MAX_CHARS,
    overlap_chars=chunking.DEFAULT_OVERLAP_CHARS,
    separators=None,
    remove_urls=False,
    collapse_whitespace=False,
    embedding_provider=None,
    vector_store=None,
):
    row = _material_row(connection, material_id)
    if row is None:
        raise IndexingError("material not found")

    old_ids = [item["id"] for item in db.list_knowledge_chunks(material_id, connection=connection)]
    if vector_store is not None and old_ids:
        try:
            vector_store.delete(old_ids)
        except VectorStoreError:
            # SQLite remains authoritative; reconcile will retry vector cleanup.
            pass

    db.delete_knowledge_chunks(connection, material_id)
    chunks = chunking.chunk_text(
        row["body_text"],
        strategy=strategy,
        max_chars=max_chars,
        overlap_chars=overlap_chars,
        separators=separators,
        remove_urls=remove_urls,
        collapse_whitespace=collapse_whitespace,
    )
    chunk_ids = []
    try:
        for chunk in chunks:
            chunk_ids.append(
                db.insert_knowledge_chunk(
                    connection,
                    knowledge_entry_id=row["knowledge_entry_id"],
                    material_id=row["id"],
                    class_id=row["class_id"],
                    chunk=chunk,
                )
            )
        connection.commit()
    except Exception as error:
        connection.rollback()
        raise IndexingError("could not persist knowledge chunks") from error

    if not chunk_ids:
        return {"material_id": material_id, "chunk_ids": [], "vector_status": "unavailable"}

    if embedding_provider is None or vector_store is None:
        db.update_chunk_vector_status(
            connection,
            chunk_ids,
            "unavailable",
            "vector indexing is not configured",
        )
        connection.commit()
        return {"material_id": material_id, "chunk_ids": chunk_ids, "vector_status": "unavailable"}

    try:
        texts = [chunk.text for chunk in chunks]
        vectors = embedding_provider.embed(texts)
        if len(vectors) != len(chunk_ids) or not vectors:
            raise EmbeddingProviderError("embedding count does not match chunk count")
        dimensions = len(vectors[0])
        if any(len(vector) != dimensions for vector in vectors):
            raise EmbeddingProviderError("embedding dimensions are inconsistent")
        vector_store.ensure_collection(dimensions)
        points = [
            (
                chunk_id,
                vector,
                _vector_payload(row, chunk_id, chunk.index),
            )
            for chunk_id, chunk, vector in zip(chunk_ids, chunks, vectors)
        ]
        vector_store.upsert(points)
    except (EmbeddingProviderError, VectorStoreError, OSError, RuntimeError) as error:
        try:
            vector_store.delete(chunk_ids)
        except Exception:
            pass
        db.update_chunk_vector_status(connection, chunk_ids, "failed", str(error))
        connection.commit()
        return {
            "material_id": material_id,
            "chunk_ids": chunk_ids,
            "vector_status": "failed",
            "error": str(error),
        }

    db.update_chunk_vector_status(connection, chunk_ids, "ready", None)
    connection.commit()
    return {"material_id": material_id, "chunk_ids": chunk_ids, "vector_status": "ready"}


def reconcile(connection, *, embedding_provider=None, vector_store=None):
    rows = connection.execute("SELECT id FROM materials ORDER BY id").fetchall()
    rebuilt = []
    for row in rows:
        chunks = db.list_knowledge_chunks(row["id"], connection=connection)
        needs_rebuild = not chunks or any(
            chunk["index_status"] != "ready"
            or (embedding_provider is not None and vector_store is not None and chunk["vector_status"] != "ready")
            for chunk in chunks
        )
        if needs_rebuild:
            rebuilt.append(
                rebuild_material(
                    connection,
                    row["id"],
                    embedding_provider=embedding_provider,
                    vector_store=vector_store,
                )
            )
    return rebuilt


def remove_material_index(connection, material_id, *, vector_store=None):
    chunk_ids = [
        row["id"]
        for row in db.list_knowledge_chunks(material_id, connection=connection)
    ]
    if vector_store is not None and chunk_ids:
        try:
            vector_store.delete(chunk_ids)
        except VectorStoreError:
            pass
    db.delete_knowledge_chunks(connection, material_id)


def material_content_hash(body_text):
    return hashlib.sha256(body_text.encode("utf-8")).hexdigest()
