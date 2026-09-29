"""Small vector-store and embedding adapters with no browser-facing dependency."""

from __future__ import annotations

import hashlib
import json
import math
import re
import urllib.error
import urllib.request


class VectorStoreError(RuntimeError):
    pass


class VectorStoreUnavailable(VectorStoreError):
    pass


class EmbeddingProviderError(RuntimeError):
    pass


class HashEmbeddingProvider:
    """Deterministic offline provider for tests and local demonstrations."""

    dimensions = 32

    def embed(self, texts):
        vectors = []
        for text in texts:
            vector = [0.0] * self.dimensions
            tokens = re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]", text.lower())
            if not tokens:
                tokens = list(text)
            for token in tokens:
                digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
                index = int.from_bytes(digest[:4], "big") % self.dimensions
                sign = 1.0 if digest[4] % 2 else -1.0
                vector[index] += sign
            norm = math.sqrt(sum(value * value for value in vector)) or 1.0
            vectors.append([value / norm for value in vector])
        return vectors


class HttpEmbeddingProvider:
    def __init__(self, url, *, api_key=None, timeout=10):
        self.url = url
        self.api_key = api_key
        self.timeout = timeout
        self.dimensions = None

    def embed(self, texts):
        body = json.dumps({"input": list(texts)}).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(self.url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as error:
            raise EmbeddingProviderError("embedding service unavailable") from error
        data = payload.get("data") or payload.get("embeddings")
        if not isinstance(data, list):
            raise EmbeddingProviderError("embedding response has no data")
        vectors = []
        for item in data:
            vector = item.get("embedding") if isinstance(item, dict) else item
            if not isinstance(vector, list) or not vector:
                raise EmbeddingProviderError("embedding response has invalid vector")
            vectors.append([float(value) for value in vector])
        if vectors:
            self.dimensions = len(vectors[0])
        return vectors


class InMemoryVectorStore:
    """Test double implementing the same contract as the Qdrant adapter."""

    def __init__(self):
        self.points = {}
        self.dimensions = None

    def ensure_collection(self, dimensions):
        self.dimensions = dimensions

    def upsert(self, points):
        for point_id, vector, payload in points:
            if self.dimensions is not None and len(vector) != self.dimensions:
                raise VectorStoreError("vector dimension mismatch")
            self.points[int(point_id)] = (list(vector), dict(payload))

    def delete(self, point_ids):
        for point_id in point_ids:
            self.points.pop(int(point_id), None)

    def search(self, vector, class_id, limit, score_threshold=0.35):
        query_norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        results = []
        for point_id, (candidate, payload) in self.points.items():
            if payload.get("class_id") != class_id:
                continue
            candidate_norm = math.sqrt(sum(value * value for value in candidate)) or 1.0
            score = sum(a * b for a, b in zip(vector, candidate)) / (query_norm * candidate_norm)
            if score >= score_threshold:
                results.append({"id": point_id, "score": score, "payload": payload})
        return sorted(results, key=lambda item: (-item["score"], item["id"]))[:limit]


class QdrantVectorStore:
    def __init__(self, base_url, *, collection="campusclaw_chunks", timeout=10):
        self.base_url = base_url.rstrip("/")
        self.collection = collection
        self.timeout = timeout
        self.dimensions = None

    def _request(self, method, path, payload=None):
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        request = urllib.request.Request(
            f"{self.base_url}{path}", data=body, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
                return json.loads(raw.decode("utf-8")) if raw else {}
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as error:
            raise VectorStoreUnavailable("vector service unavailable") from error

    def ensure_collection(self, dimensions):
        self.dimensions = dimensions
        try:
            self._request("GET", f"/collections/{self.collection}")
        except VectorStoreUnavailable as error:
            if not isinstance(error.__cause__, urllib.error.HTTPError) or error.__cause__.code != 404:
                raise
            self._request(
                "PUT",
                f"/collections/{self.collection}",
                {"vectors": {"size": dimensions, "distance": "Cosine"}},
            )

    def upsert(self, points):
        payload = {
            "points": [
                {"id": int(point_id), "vector": vector, "payload": metadata}
                for point_id, vector, metadata in points
            ]
        }
        self._request("PUT", f"/collections/{self.collection}/points?wait=true", payload)

    def delete(self, point_ids):
        if point_ids:
            self._request(
                "POST",
                f"/collections/{self.collection}/points/delete?wait=true",
                {"points": [int(point_id) for point_id in point_ids]},
            )

    def search(self, vector, class_id, limit, score_threshold=0.35):
        payload = {
            "vector": vector,
            "limit": limit,
            "with_payload": True,
            "score_threshold": score_threshold,
            "filter": {"must": [{"key": "class_id", "match": {"value": class_id}}]},
        }
        response = self._request("POST", f"/collections/{self.collection}/points/search", payload)
        return [
            {"id": item.get("id"), "score": item.get("score", 0.0), "payload": item.get("payload") or {}}
            for item in response.get("result", [])
        ]


def build_embedding_provider(config):
    configured = config.get("EMBEDDING_PROVIDER")
    if configured is not None and hasattr(configured, "embed"):
        return configured
    if config.get("EMBEDDING_MODE", "http") == "hash":
        return HashEmbeddingProvider()
    url = config.get("EMBEDDING_API_URL")
    if not url:
        return None
    return HttpEmbeddingProvider(
        url,
        api_key=config.get("EMBEDDING_API_KEY"),
        timeout=float(config.get("EMBEDDING_TIMEOUT", 10)),
    )


def build_vector_store(config):
    configured = config.get("VECTOR_STORE")
    if configured is not None and hasattr(configured, "search"):
        return configured
    if config.get("VECTOR_STORE_MODE") == "memory":
        return InMemoryVectorStore()
    url = config.get("QDRANT_URL")
    if not url:
        return None
    return QdrantVectorStore(
        url,
        collection=config.get("QDRANT_COLLECTION", "campusclaw_chunks"),
        timeout=float(config.get("QDRANT_TIMEOUT", 10)),
    )
