"""Class-scoped keyword, vector and hybrid retrieval orchestration."""

from __future__ import annotations

from collections import defaultdict

from . import db
from .vector_store import EmbeddingProviderError, VectorStoreError


DEFAULT_MODE = "hybrid"
DEFAULT_LIMIT = 10
MAX_LIMIT = 20
VECTOR_THRESHOLD = 0.35
RRF_K = 60
NOT_FOUND_MESSAGE = "资料中未找到相关内容"


class RetrievalUnavailable(RuntimeError):
    pass


def normalize_request(query, mode=DEFAULT_MODE, limit=DEFAULT_LIMIT):
    query = (query or "").strip()
    if not query:
        raise ValueError("query is required")
    mode = (mode or DEFAULT_MODE).strip().lower()
    if mode not in {"keyword", "vector", "hybrid"}:
        raise ValueError("unsupported retrieval mode")
    try:
        limit = int(limit)
    except (TypeError, ValueError) as error:
        raise ValueError("limit must be an integer") from error
    if limit < 1 or limit > MAX_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_LIMIT}")
    return query, mode, limit


def _keyword(connection, class_id, query, limit):
    return list(db.search_knowledge_keyword(connection, class_id, query, limit))


def _vector(connection, class_id, query, limit, *, embedding_provider, vector_store):
    if embedding_provider is None or vector_store is None:
        raise RetrievalUnavailable("vector retrieval is not configured")
    try:
        vectors = embedding_provider.embed([query])
        if len(vectors) != 1 or not vectors[0]:
            raise RetrievalUnavailable("embedding service returned no vector")
        candidates = vector_store.search(
            vectors[0], class_id, limit, score_threshold=VECTOR_THRESHOLD
        )
    except RetrievalUnavailable:
        raise
    except (EmbeddingProviderError, VectorStoreError, OSError, RuntimeError) as error:
        raise RetrievalUnavailable("vector retrieval is unavailable") from error
    candidates = [
        candidate
        for candidate in candidates
        if float(candidate.get("score", 0.0)) >= VECTOR_THRESHOLD
    ]
    ids = [int(candidate["id"]) for candidate in candidates if candidate.get("id") is not None]
    rows = db.get_chunks_by_ids(connection, class_id, ids)
    by_id = {row["id"]: row for row in rows}
    return [
        (by_id[int(candidate["id"])], float(candidate.get("score", 0.0)))
        for candidate in candidates
        if int(candidate["id"]) in by_id
    ]


def search(
    connection,
    class_id,
    query,
    *,
    mode=DEFAULT_MODE,
    limit=DEFAULT_LIMIT,
    embedding_provider=None,
    vector_store=None,
):
    query, mode, limit = normalize_request(query, mode, limit)
    if mode == "keyword":
        rows = _keyword(connection, class_id, query, limit)
        hits = [(row, None, {"keyword"}) for row in rows]
    elif mode == "vector":
        hits = [(row, score, {"vector"}) for row, score in _vector(
            connection,
            class_id,
            query,
            limit,
            embedding_provider=embedding_provider,
            vector_store=vector_store,
        )]
    else:
        keyword_rows = _keyword(connection, class_id, query, limit * 3)
        vector_rows = _vector(
            connection,
            class_id,
            query,
            limit * 3,
            embedding_provider=embedding_provider,
            vector_store=vector_store,
        )
        fused = defaultdict(lambda: {"score": 0.0, "modes": set(), "row": None})
        for rank, row in enumerate(keyword_rows, start=1):
            item = fused[row["id"]]
            item["row"] = row
            item["score"] += 1.0 / (RRF_K + rank)
            item["modes"].add("keyword")
        for rank, (row, _vector_score) in enumerate(vector_rows, start=1):
            item = fused[row["id"]]
            item["row"] = row
            item["score"] += 1.0 / (RRF_K + rank)
            item["modes"].add("vector")
        ordered = sorted(
            fused.values(),
            key=lambda item: (-item["score"], item["row"]["id"]),
        )[:limit]
        hits = [(item["row"], item["score"], item["modes"]) for item in ordered]
    return {
        "query": query,
        "mode": mode,
        "hits": hits,
        "message": None if hits else NOT_FOUND_MESSAGE,
    }
