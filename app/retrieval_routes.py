from flask import Blueprint, current_app, jsonify, request, url_for

from . import db, retrieval
from .answer import AnswerProviderError, answer_with_configuration, normalize_citations
from .auth import current_user, login_required
from .skill_registry import select_skills


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
    connection = db.get_db()
    query = request.args.get("q", "")
    registry = current_app.extensions.get("skill_registry", {})
    skill_selection = select_skills(
        registry,
        db.list_assistant_skills(connection, user["class_id"]),
        query,
        current_app.config["SKILL_INSTRUCTION_TOKEN_BUDGET"],
        settings_version=db.get_assistant_skill_settings_version(connection, user["class_id"]),
    )
    audit_id = db.create_audit_operation(
        connection,
        user_id=user["id"],
        class_id=user["class_id"],
        operation="search",
        skill_decisions=skill_selection["decisions"],
    )
    try:
        result = retrieval.search(
            connection,
            user["class_id"],
            query,
            mode=request.args.get("mode", retrieval.DEFAULT_MODE),
            limit=request.args.get("limit", retrieval.DEFAULT_LIMIT),
            embedding_provider=current_app.extensions.get("knowledge_embedding_provider"),
            vector_store=current_app.extensions.get("knowledge_vector_store"),
        )
    except ValueError as error:
        db.finish_audit_operation(connection, audit_id, "failed")
        return jsonify({"error": str(error)}), 400
    except retrieval.RetrievalUnavailable as error:
        db.finish_audit_operation(connection, audit_id, "failed")
        return jsonify({"error": str(error)}), 503
    except Exception as error:
        db.finish_audit_operation(connection, audit_id, "failed")
        current_app.logger.warning("Knowledge search failed: %s", type(error).__name__)
        return jsonify({"error": "retrieval service unavailable"}), 503
    db.record_audit_hits(connection, audit_id, result["hits"])
    db.finish_audit_operation(
        connection, audit_id, "complete" if result["hits"] else "no-evidence"
    )
    return jsonify(
        {
            "audit_id": audit_id,
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
    raw_question = payload.get("question") or payload.get("message") or ""
    if not isinstance(raw_question, str) or not raw_question.strip():
        return jsonify({"error": "question is required"}), 400
    question = raw_question.strip()
    raw_history = payload.get("history")
    history = []
    if isinstance(raw_history, list):
        for message in raw_history:
            if not isinstance(message, dict) or message.get("role") not in {"user", "assistant"}:
                continue
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                history.append({"role": message["role"], "content": content.strip()})
    connection = db.get_db()
    assistant_config = db.get_assistant_config(connection, user["class_id"])
    settings = db.list_assistant_skills(connection, user["class_id"])
    registry = current_app.extensions.get("skill_registry", {})
    skill_selection = select_skills(
        registry,
        settings,
        question,
        current_app.config["SKILL_INSTRUCTION_TOKEN_BUDGET"],
        settings_version=db.get_assistant_skill_settings_version(connection, user["class_id"]),
    )
    audit_id = db.create_audit_operation(
        connection,
        user_id=user["id"],
        class_id=user["class_id"],
        operation="ask",
        skill_decisions=skill_selection["decisions"],
    )
    if assistant_config is None:
        db.finish_audit_operation(connection, audit_id, "failed")
        return jsonify({"error": "assistant settings unavailable", "audit_id": audit_id}), 503
    try:
        result = retrieval.search(
            connection,
            user["class_id"],
            question,
            mode="hybrid",
            limit=4,
            embedding_provider=current_app.extensions.get("knowledge_embedding_provider"),
            vector_store=current_app.extensions.get("knowledge_vector_store"),
        )
    except ValueError as error:
        db.finish_audit_operation(connection, audit_id, "failed")
        return jsonify({"error": str(error)}), 400
    except retrieval.RetrievalUnavailable as error:
        db.finish_audit_operation(connection, audit_id, "failed")
        return jsonify({"error": str(error)}), 503
    except Exception as error:
        db.finish_audit_operation(connection, audit_id, "failed")
        current_app.logger.warning("Assistant retrieval failed: %s", type(error).__name__)
        return jsonify({"error": "retrieval service unavailable"}), 503

    hits = result["hits"][:4]
    db.record_audit_hits(connection, audit_id, hits)
    if not hits:
        db.finish_audit_operation(connection, audit_id, "no-evidence")
        return jsonify({"answer": retrieval.NOT_FOUND_MESSAGE, "citations": [], "audit_id": audit_id})

    provider = current_app.extensions.get("answer_provider")
    if provider is None:
        db.finish_audit_operation(connection, audit_id, "failed")
        return jsonify({"error": "answer service is unavailable", "audit_id": audit_id}), 503
    contexts = [
        {
            "title": row["title"],
            "chunk_index": row["chunk_index"],
            "chunk_text": row["chunk_text"],
        }
        for row, _score, _modes in hits
    ]
    try:
        answer_text = answer_with_configuration(
            provider,
            question,
            contexts,
            history,
            system_prompt=assistant_config["prompt"],
            skill_instruction=skill_selection["instruction"],
        )
        if isinstance(answer_text, dict):
            answer_text = answer_text.get("answer", "")
        answer_text, references = normalize_citations(answer_text, len(contexts))
    except (AnswerProviderError, OSError, RuntimeError) as error:
        db.finish_audit_operation(connection, audit_id, "failed")
        return jsonify({"error": "answer service unavailable", "audit_id": audit_id}), 503
    except Exception as error:
        db.finish_audit_operation(connection, audit_id, "failed")
        current_app.logger.warning("Single-turn answer failed: %s", type(error).__name__)
        return jsonify({"error": "answer service unavailable", "audit_id": audit_id}), 503
    citations = []
    for reference in references:
        row, score, modes = hits[reference - 1]
        citation = hit_json(row, score, modes)
        citation["index"] = reference
        citations.append(citation)
    citation_indexes = {hits[reference - 1][0]["id"]: reference for reference in references}
    db.record_audit_hits(connection, audit_id, hits, citation_indexes)
    db.finish_audit_operation(connection, audit_id, "complete")
    return jsonify({"answer": answer_text, "citations": citations, "audit_id": audit_id})
