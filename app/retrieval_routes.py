from flask import Blueprint, current_app, jsonify, request, url_for

from . import db, retrieval
from .answer import AnswerProviderError, normalize_citations
from .auth import current_user, login_required


bp = Blueprint("retrieval", __name__)


def hit_json(row, score=None, modes=None):
    source = {
        "material_id": row["material_id"],
        "title": row["title"],
        "chunk_index": row["chunk_index"],
        "start_offset": row["start_offset"],
        "end_offset": row["end_offset"],
        "offset_basis": row["offset_basis"],
        "strategy": row["strategy"],
        "preview_url": url_for("materials.material_detail", material_id=row["material_id"]),
        "download_url": url_for("materials.material_download", material_id=row["material_id"]),
    }
    result = {"snippet": row["chunk_text"], "source": source}
    if score is not None:
        result["score"] = round(float(score), 8)
    if modes:
        result["matched_modes"] = sorted(modes)
    return result


@bp.get("/api/knowledge/search")
@login_required
def knowledge_search():
    user = current_user()
    try:
        result = retrieval.search(
            db.get_db(),
            user["class_id"],
            request.args.get("q", ""),
            mode=request.args.get("mode", retrieval.DEFAULT_MODE),
            limit=request.args.get("limit", retrieval.DEFAULT_LIMIT),
            embedding_provider=current_app.extensions.get("knowledge_embedding_provider"),
            vector_store=current_app.extensions.get("knowledge_vector_store"),
        )
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    except retrieval.RetrievalUnavailable as error:
        return jsonify({"error": str(error)}), 503
    return jsonify(
        {
            "query": result["query"],
            "mode": result["mode"],
            "message": result["message"],
            "hits": [hit_json(row, score, modes) for row, score, modes in result["hits"]],
        }
    )


@bp.post("/api/ask")
@login_required
def ask():
    user = current_user()
    payload = request.get_json(silent=True) or {}
    question = (payload.get("question") or payload.get("message") or "").strip()
    if not question:
        return jsonify({"error": "question is required"}), 400
    raw_history = payload.get("history")
    history = []
    if isinstance(raw_history, list):
        for message in raw_history:
            if not isinstance(message, dict) or message.get("role") not in {"user", "assistant"}:
                continue
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                history.append({"role": message["role"], "content": content.strip()})
    try:
        result = retrieval.search(
            db.get_db(),
            user["class_id"],
            question,
            mode="hybrid",
            limit=4,
            embedding_provider=current_app.extensions.get("knowledge_embedding_provider"),
            vector_store=current_app.extensions.get("knowledge_vector_store"),
        )
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    except retrieval.RetrievalUnavailable as error:
        return jsonify({"error": str(error)}), 503

    if not result["hits"]:
        return jsonify({"answer": retrieval.NOT_FOUND_MESSAGE, "citations": []})

    provider = current_app.extensions.get("answer_provider")
    if provider is None:
        return jsonify({"error": "answer service is unavailable"}), 503
    contexts = [
        {
            "title": row["title"],
            "chunk_index": row["chunk_index"],
            "chunk_text": row["chunk_text"],
        }
        for row, _score, _modes in result["hits"]
    ]
    try:
        answer_text = provider.answer(question, contexts, history)
        if isinstance(answer_text, dict):
            answer_text = answer_text.get("answer", "")
        answer_text, references = normalize_citations(answer_text, len(contexts))
    except (AnswerProviderError, OSError, RuntimeError) as error:
        return jsonify({"error": str(error) or "answer service is unavailable"}), 503
    citations = []
    for reference in references:
        row, score, modes = result["hits"][reference - 1]
        citation = hit_json(row, score, modes)
        citation["index"] = reference
        citations.append(citation)
    return jsonify({"answer": answer_text, "citations": citations})
