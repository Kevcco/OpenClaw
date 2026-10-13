"""Teacher-managed assistant configuration and persistent guided conversations."""

import json

from flask import Blueprint, Response, abort, current_app, jsonify, request, stream_with_context

from . import db, retrieval
from .answer import AnswerProviderError, answer_with_configuration, normalize_citations
from .auth import admin_required, current_user, login_required, role_required
from .skill_registry import select_skills
from .retrieval_routes import hit_json


bp = Blueprint("assistant", __name__)
MAX_PROMPT_CHARS = 6000
MAX_QUESTION_CHARS = 4000
MAX_CONVERSATION_TITLE_CHARS = 120
SOLUTION_GUIDANCE_KEY = "solution-guidance"


def _config_json(row):
    return {
        "prompt": row["prompt"],
        "prompt_version": row["prompt_version"],
        "updated_at": row["updated_at"],
    }


def _skill_json(row):
    return {
        "key": row["skill_key"],
        "name": row["name"],
        "instruction": row["instruction"],
        "enabled": bool(row["enabled"]),
        "version": row["version"],
        "updated_at": row["updated_at"],
    }


def _registered_skill_json(package, setting):
    return {
        "key": package["key"],
        "name": package["name"],
        "summary": package["summary"],
        "package_version": package["version"],
        "enabled": bool(setting["enabled"]),
        "version": setting["version"],
        "updated_at": setting["updated_at"],
    }


def _conversation_json(row):
    return {
        "id": row["id"],
        "title": row["title"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _message_json(row):
    try:
        citations = json.loads(row["citations_json"] or "[]")
    except (TypeError, json.JSONDecodeError):
        citations = []
    try:
        skill_snapshot = json.loads(row["skill_snapshot_json"] or "{}")
    except (KeyError, TypeError, json.JSONDecodeError):
        skill_snapshot = {}
    return {
        "id": row["id"],
        "role": row["role"],
        "content": row["content"],
        "status": row["status"],
        "citations": citations,
        "created_at": row["created_at"],
        "prompt_version": row["prompt_version"],
        "skill_version": row["skill_version"],
        "skill_snapshot": skill_snapshot,
    }


@bp.route("/api/assistant/settings", methods=("GET", "PUT"))
@role_required("teacher")
def assistant_settings():
    user = current_user()
    connection = db.get_db()
    config = db.get_assistant_config(connection, user["class_id"])
    if config is None:
        return jsonify({"error": "assistant settings unavailable"}), 503
    if request.method == "GET":
        return jsonify(_config_json(config))

    payload = request.get_json(silent=True) or {}
    prompt = payload.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return jsonify({"error": "prompt is required"}), 400
    prompt = prompt.strip()
    if len(prompt) > MAX_PROMPT_CHARS:
        return jsonify({"error": f"prompt must be at most {MAX_PROMPT_CHARS} characters"}), 400
    updated = db.update_assistant_prompt(connection, user["class_id"], prompt)
    return jsonify(_config_json(updated))


@bp.route("/api/assistant/skills/solution-guidance", methods=("GET", "PATCH"))
@role_required("teacher")
def solution_guidance_skill():
    return _skill_setting(SOLUTION_GUIDANCE_KEY, update=request.method == "PATCH")


@bp.get("/api/assistant/skills")
@role_required("teacher")
def assistant_skills():
    user = current_user()
    registry = current_app.extensions.get("skill_registry", {})
    rows = db.list_assistant_skills(db.get_db(), user["class_id"])
    settings = {row["skill_key"]: row for row in rows}
    return jsonify(
        {
            "skills": [
                _registered_skill_json(package, settings[key])
                for key, package in sorted(registry.items())
                if key in settings
            ]
        }
    )


@bp.patch("/api/assistant/skills/<skill_key>")
@role_required("teacher")
def update_assistant_skill(skill_key):
    return _skill_setting(skill_key, update=True)


@bp.get("/api/admin/audits")
@admin_required
def admin_audits():
    integer_filters = ("class_id", "user_id", "material_id", "chunk_id")
    filters = {}
    for name in integer_filters:
        raw = request.args.get(name)
        if raw is None:
            continue
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return jsonify({"error": f"{name} must be an integer"}), 400
        if value < 1:
            return jsonify({"error": f"{name} must be positive"}), 400
        filters[name] = value
    for name in ("audit_id", "operation", "status", "created_after", "created_before", "skill_key"):
        value = request.args.get(name)
        if value:
            value = value.strip()
            if len(value) > 200:
                return jsonify({"error": f"{name} is too long"}), 400
            filters[name] = value
    if filters.get("operation") not in {None, "search", "ask", "conversation"}:
        return jsonify({"error": "operation is invalid"}), 400
    if filters.get("status") not in {None, "processing", "complete", "no-evidence", "failed", "interrupted"}:
        return jsonify({"error": "status is invalid"}), 400
    try:
        limit = int(request.args.get("limit", "50"))
        offset = int(request.args.get("offset", "0"))
    except (TypeError, ValueError):
        return jsonify({"error": "limit and offset must be integers"}), 400
    if not 1 <= limit <= 100 or not 0 <= offset <= 100000:
        return jsonify({"error": "limit must be 1..100 and offset 0..100000"}), 400
    audits = db.list_audit_operations(db.get_db(), filters, limit=limit, offset=offset)
    return jsonify({"audits": audits, "limit": limit, "offset": offset})


def _skill_setting(skill_key, update=False):
    user = current_user()
    connection = db.get_db()
    package = current_app.extensions.get("skill_registry", {}).get(skill_key)
    skill = db.get_assistant_skill(connection, user["class_id"], skill_key)
    if skill is None or package is None:
        return jsonify({"error": "skill unavailable"}), 404
    if not update:
        return jsonify(_registered_skill_json(package, skill))

    payload = request.get_json(silent=True) or {}
    enabled = payload.get("enabled")
    if not isinstance(enabled, bool):
        return jsonify({"error": "enabled must be a boolean"}), 400
    updated = db.update_assistant_skill(
        connection, user["class_id"], enabled, skill_key
    )
    return jsonify(_registered_skill_json(package, updated))


@bp.route("/api/conversations", methods=("GET", "POST"))
@login_required
def conversations():
    user = current_user()
    connection = db.get_db()
    if request.method == "GET":
        try:
            limit = int(request.args.get("limit", "50"))
        except (TypeError, ValueError):
            return jsonify({"error": "limit must be an integer"}), 400
        if not 1 <= limit <= 100:
            return jsonify({"error": "limit must be between 1 and 100"}), 400
        rows = db.list_conversations(connection, user["id"], user["class_id"], limit)
        return jsonify({"conversations": [_conversation_json(row) for row in rows]})

    payload = request.get_json(silent=True) or {}
    title = payload.get("title", "新对话")
    if not isinstance(title, str):
        return jsonify({"error": "title must be a string"}), 400
    title = title.strip() or "新对话"
    if len(title) > MAX_CONVERSATION_TITLE_CHARS:
        return jsonify({"error": f"title must be at most {MAX_CONVERSATION_TITLE_CHARS} characters"}), 400
    row = db.create_conversation(connection, user["id"], user["class_id"], title)
    return jsonify({"conversation": _conversation_json(row)}), 201


@bp.route("/api/conversations/<int:conversation_id>", methods=("GET", "DELETE"))
@login_required
def conversation_detail(conversation_id):
    user = current_user()
    connection = db.get_db()
    row = db.get_conversation(connection, conversation_id, user["id"], user["class_id"])
    if row is None:
        return jsonify({"error": "not found"}), 404
    if request.method == "DELETE":
        db.delete_conversation(connection, conversation_id, user["id"], user["class_id"])
        return jsonify({"status": "deleted"})
    messages = db.list_conversation_messages(
        connection, conversation_id, user["id"], user["class_id"]
    )
    return jsonify(
        {
            "conversation": _conversation_json(row),
            "messages": [_message_json(message) for message in messages],
        }
    )


def _sse(event, payload):
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {data}\n\n"


def _mark_failed(connection, message_id, user, message):
    db.update_conversation_message(
        connection,
        message_id,
        user["id"],
        user["class_id"],
        content=message,
        status="failed",
    )


@bp.post("/api/conversations/<int:conversation_id>/messages/stream")
@login_required
def stream_conversation_message(conversation_id):
    user = current_user()
    connection = db.get_db()
    conversation = db.get_conversation(
        connection, conversation_id, user["id"], user["class_id"]
    )
    if conversation is None:
        return jsonify({"error": "not found"}), 404

    payload = request.get_json(silent=True) or {}
    question = payload.get("question")
    if not isinstance(question, str) or not question.strip():
        return jsonify({"error": "question is required"}), 400
    question = question.strip()
    if len(question) > MAX_QUESTION_CHARS:
        return jsonify({"error": f"question must be at most {MAX_QUESTION_CHARS} characters"}), 400

    assistant_config = db.get_assistant_config(connection, user["class_id"])
    settings = db.list_assistant_skills(connection, user["class_id"])
    if assistant_config is None:
        return jsonify({"error": "assistant settings unavailable"}), 503
    skill_selection = select_skills(
        current_app.extensions.get("skill_registry", {}),
        settings,
        question,
        current_app.config["SKILL_INSTRUCTION_TOKEN_BUDGET"],
        settings_version=db.get_assistant_skill_settings_version(connection, user["class_id"]),
    )
    skill_version = skill_selection["setting_version"]

    prior_rows = db.list_conversation_messages(
        connection, conversation_id, user["id"], user["class_id"]
    )
    history = [
        {"role": row["role"], "content": row["content"][:4000]}
        for row in prior_rows
        if row["status"] == "complete" and row["role"] in {"user", "assistant"}
    ][-20:]
    _user_message_id, assistant_message_id = db.create_conversation_turn(
        connection,
        conversation_id=conversation_id,
        owner_user_id=user["id"],
        class_id=user["class_id"],
        question=question,
        prompt_version=assistant_config["prompt_version"],
        skill_version=skill_version,
        skill_snapshot=skill_selection["snapshot"],
    )
    db.update_conversation_message(
        connection,
        assistant_message_id,
        user["id"],
        user["class_id"],
        content="",
        status="streaming",
    )
    audit_id = db.create_audit_operation(
        connection,
        user_id=user["id"],
        class_id=user["class_id"],
        operation="conversation",
        skill_decisions=skill_selection["decisions"],
        conversation_message_id=assistant_message_id,
    )

    def generate():
        stream_connection = db.connect(current_app.config["DATABASE_PATH"])
        try:
            yield _sse("start", {"message_id": assistant_message_id, "audit_id": audit_id})
            result = retrieval.search(
                stream_connection,
                user["class_id"],
                question,
                mode="hybrid",
                limit=4,
                embedding_provider=current_app.extensions.get("knowledge_embedding_provider"),
                vector_store=current_app.extensions.get("knowledge_vector_store"),
            )
            hits = result["hits"][:4]
            db.record_audit_hits(stream_connection, audit_id, hits)
            if not hits:
                final_answer = retrieval.NOT_FOUND_MESSAGE
                citations = []
                db.update_conversation_message(
                    stream_connection,
                    assistant_message_id,
                    user["id"],
                    user["class_id"],
                    content=final_answer,
                    status="complete",
                    citations=citations,
                )
                db.finish_audit_operation(stream_connection, audit_id, "no-evidence")
                yield _sse("delta", {"text": final_answer})
                yield _sse(
                    "done",
                    {"message_id": assistant_message_id, "answer": final_answer, "citations": citations, "audit_id": audit_id},
                )
                return

            contexts = [
                {"title": row["title"], "chunk_index": row["chunk_index"], "chunk_text": row["chunk_text"]}
                for row, _score, _modes in hits
            ]
            provider = current_app.extensions.get("answer_provider")
            if provider is None:
                raise AnswerProviderError("answer service unavailable")
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
            if not isinstance(answer_text, str) or not answer_text.strip():
                raise AnswerProviderError("answer service returned no answer")
            answer_text, references = normalize_citations(answer_text, len(contexts))
            citations = []
            for reference in references:
                row, score, modes = hits[reference - 1]
                citation = hit_json(row, score, modes)
                citation["index"] = reference
                citations.append(citation)

            db.update_conversation_message(
                stream_connection,
                assistant_message_id,
                user["id"],
                user["class_id"],
                content=answer_text,
                status="complete",
                citations=citations,
            )
            citation_indexes = {
                hits[reference - 1][0]["id"]: reference for reference in references
            }
            db.record_audit_hits(stream_connection, audit_id, hits, citation_indexes)
            db.finish_audit_operation(stream_connection, audit_id, "complete")
            for offset in range(0, len(answer_text), 40):
                yield _sse("delta", {"text": answer_text[offset : offset + 40]})
            yield _sse(
                "done",
                {"message_id": assistant_message_id, "answer": answer_text, "citations": citations, "audit_id": audit_id},
            )
        except GeneratorExit:
            _mark_failed(stream_connection, assistant_message_id, user, "回答流已中断")
            db.finish_audit_operation(stream_connection, audit_id, "interrupted")
            raise
        except (retrieval.RetrievalUnavailable, AnswerProviderError, OSError, RuntimeError, ValueError) as error:
            _mark_failed(stream_connection, assistant_message_id, user, "回答暂不可用，请稍后重试。")
            db.finish_audit_operation(stream_connection, audit_id, "failed")
            current_app.logger.warning("Assistant stream failed: %s", type(error).__name__)
            yield _sse(
                "error",
                {"message_id": assistant_message_id, "error": "回答暂不可用，请稍后重试。", "audit_id": audit_id},
            )
        except Exception as error:
            _mark_failed(stream_connection, assistant_message_id, user, "回答暂不可用，请稍后重试。")
            db.finish_audit_operation(stream_connection, audit_id, "failed")
            current_app.logger.warning("Assistant stream failed: %s", type(error).__name__)
            yield _sse(
                "error",
                {"message_id": assistant_message_id, "error": "回答暂不可用，请稍后重试。", "audit_id": audit_id},
            )
        finally:
            stream_connection.close()

    response = Response(stream_with_context(generate()), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache, no-transform"
    response.headers["X-Accel-Buffering"] = "no"
    return response
