"""Teacher-managed assistant configuration and persistent guided conversations."""

import json

from flask import Blueprint, Response, abort, current_app, jsonify, request, stream_with_context

from . import db, retrieval
from .answer import AnswerProviderError, answer_with_configuration, normalize_citations
from .auth import current_user, login_required, role_required
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
    return {
        "id": row["id"],
        "role": row["role"],
        "content": row["content"],
        "status": row["status"],
        "citations": citations,
        "created_at": row["created_at"],
        "prompt_version": row["prompt_version"],
        "skill_version": row["skill_version"],
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
    user = current_user()
    connection = db.get_db()
    skill = db.get_assistant_skill(connection, user["class_id"], SOLUTION_GUIDANCE_KEY)
    if skill is None:
        return jsonify({"error": "solution-guidance skill unavailable"}), 503
    if request.method == "GET":
        return jsonify(_skill_json(skill))

    payload = request.get_json(silent=True) or {}
    enabled = payload.get("enabled")
    if not isinstance(enabled, bool):
        return jsonify({"error": "enabled must be a boolean"}), 400
    updated = db.update_assistant_skill(
        connection, user["class_id"], enabled, SOLUTION_GUIDANCE_KEY
    )
    return jsonify(_skill_json(updated))


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
    skill = db.get_assistant_skill(connection, user["class_id"], SOLUTION_GUIDANCE_KEY)
    if assistant_config is None or skill is None:
        return jsonify({"error": "assistant settings unavailable"}), 503

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
        skill_version=skill["version"],
    )
    db.update_conversation_message(
        connection,
        assistant_message_id,
        user["id"],
        user["class_id"],
        content="",
        status="streaming",
    )

    def generate():
        stream_connection = db.connect(current_app.config["DATABASE_PATH"])
        try:
            yield _sse("start", {"message_id": assistant_message_id})
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
                yield _sse("delta", {"text": final_answer})
                yield _sse(
                    "done",
                    {"message_id": assistant_message_id, "answer": final_answer, "citations": citations},
                )
                return

            contexts = [
                {"title": row["title"], "chunk_index": row["chunk_index"], "chunk_text": row["chunk_text"]}
                for row, _score, _modes in hits
            ]
            provider = current_app.extensions.get("answer_provider")
            if provider is None:
                raise AnswerProviderError("answer service unavailable")
            skill_instruction = skill["instruction"] if skill["enabled"] else None
            answer_text = answer_with_configuration(
                provider,
                question,
                contexts,
                history,
                system_prompt=assistant_config["prompt"],
                skill_instruction=skill_instruction,
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
            for offset in range(0, len(answer_text), 40):
                yield _sse("delta", {"text": answer_text[offset : offset + 40]})
            yield _sse(
                "done",
                {"message_id": assistant_message_id, "answer": answer_text, "citations": citations},
            )
        except GeneratorExit:
            _mark_failed(stream_connection, assistant_message_id, user, "回答流已中断")
            raise
        except (retrieval.RetrievalUnavailable, AnswerProviderError, OSError, RuntimeError, ValueError) as error:
            _mark_failed(stream_connection, assistant_message_id, user, "回答暂不可用，请稍后重试。")
            current_app.logger.warning("Assistant stream failed: %s", type(error).__name__)
            yield _sse(
                "error",
                {"message_id": assistant_message_id, "error": "回答暂不可用，请稍后重试。"},
            )
        except Exception as error:
            _mark_failed(stream_connection, assistant_message_id, user, "回答暂不可用，请稍后重试。")
            current_app.logger.warning("Assistant stream failed: %s", type(error).__name__)
            yield _sse(
                "error",
                {"message_id": assistant_message_id, "error": "回答暂不可用，请稍后重试。"},
            )
        finally:
            stream_connection.close()

    response = Response(stream_with_context(generate()), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache, no-transform"
    response.headers["X-Accel-Buffering"] = "no"
    return response
