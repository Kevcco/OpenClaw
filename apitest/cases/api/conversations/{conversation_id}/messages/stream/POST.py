import json

from support import ACCOUNTS, event_stream, login, request, row


def run():
    token, _ = login("student_a")
    username = ACCOUNTS["student_a"][0]
    user = row("SELECT id, class_id FROM users WHERE username = ?", (username,))
    created = request("POST", "/api/conversations", token=token, payload={"title": "SSE 合约测试"})
    assert created["status"] == 201
    conversation_id = created["json"]["conversation"]["id"]
    stream_path = f"/api/conversations/{conversation_id}/messages/stream"
    result = request(
        "POST",
        stream_path,
        token=token,
        payload={"question": "一次函数", "class_id": 2, "system_prompt": "伪造"},
        accept="text/event-stream",
    )
    assert result["status"] == 200
    assert "text/event-stream" in result["headers"].get("Content-Type", "")
    events = event_stream(result["text"])
    names = [name for name, _ in events]
    assert names[0] == "start" and "delta" in names and names[-1] == "done"
    done = events[-1][1]
    assert isinstance(done.get("message_id"), int)
    assert isinstance(done.get("answer"), str) and done["answer"]
    assert done.get("citations")
    assert "[1]" in done["answer"]

    message = row(
        """SELECT role, content, status, citations_json, prompt_version, skill_version
           FROM conversation_messages WHERE id = ? AND owner_user_id = ? AND class_id = ?""",
        (done["message_id"], user["id"], user["class_id"]),
    )
    assert message is not None
    assert message["role"] == "assistant" and message["status"] == "complete"
    assert message["content"] == done["answer"]
    assert json.loads(message["citations_json"]) == done["citations"]
    assert isinstance(message["prompt_version"], int)
    assert isinstance(message["skill_version"], int)
    citation = done["citations"][0]
    source = citation["source"]
    stored_chunk = row(
        """SELECT material_id FROM knowledge_chunks
           WHERE class_id = ? AND material_id = ? AND chunk_index = ?""",
        (user["class_id"], source["material_id"], source["chunk_index"]),
    )
    assert stored_chunk is not None

    no_evidence = request(
        "POST",
        stream_path,
        token=token,
        payload={"question": "完全没有相关性的内容"},
        accept="text/event-stream",
    )
    no_evidence_events = event_stream(no_evidence["text"])
    no_evidence_done = next(payload for name, payload in no_evidence_events if name == "done")
    assert no_evidence_done["citations"] == []
    assert "资料中未找到相关内容" in no_evidence_done["answer"]
    empty_snapshot = row(
        "SELECT status, citations_json FROM conversation_messages WHERE id = ?",
        (no_evidence_done["message_id"],),
    )
    assert empty_snapshot["status"] == "complete"
    assert json.loads(empty_snapshot["citations_json"]) == []
    assert request("DELETE", f"/api/conversations/{conversation_id}", token=token)["status"] == 200
    assert row("SELECT id FROM conversations WHERE id = ?", (conversation_id,)) is None
    return f"SSE order, citation/source snapshot, no-evidence behavior, and SQLite persistence verified for conversation {conversation_id}"
