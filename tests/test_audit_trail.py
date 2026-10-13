import json
import os
import subprocess
import sys
from pathlib import Path

from app import db
from app.answer import AnswerProviderError
from app.vector_store import HashEmbeddingProvider, InMemoryVectorStore


class AuditAnswerProvider:
    def __init__(self, answer="答案依据 [1]"):
        self.answer_text = answer
        self.calls = []

    def answer(self, question, contexts, history=None, *, system_prompt=None, skill_instruction=None):
        self.calls.append({"question": question, "skill_instruction": skill_instruction})
        return self.answer_text


class FailedAuditAnswerProvider:
    def answer(self, question, contexts, history=None, *, system_prompt=None, skill_instruction=None):
        raise AnswerProviderError("secret diagnostic must not be exposed")


def _seed(app):
    connection = db.connect(app.config["DATABASE_PATH"])
    db.init_schema(connection)
    db.seed_data(connection, app.config["UPLOAD_DIR"])
    connection.close()
    app.extensions["knowledge_embedding_provider"] = HashEmbeddingProvider()
    app.extensions["knowledge_vector_store"] = InMemoryVectorStore()
    app.extensions["knowledge_reconciled"] = False


def _login(client, username, password):
    response = client.post("/api/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json['access_token']}"}


def test_search_ask_and_no_evidence_are_audited_without_content(app, client):
    _seed(app)
    app.extensions["answer_provider"] = AuditAnswerProvider()
    student = _login(client, "student_a1", "student_a1_pass")

    search = client.get("/api/knowledge/search?q=一次函数&mode=keyword", headers=student)
    ask = client.post("/api/ask", headers=student, json={"question": "一次函数"})
    missing = client.post("/api/ask", headers=student, json={"question": "没有命中的冷门话题"})

    assert search.status_code == ask.status_code == missing.status_code == 200
    assert search.json["audit_id"] and ask.json["audit_id"] and missing.json["audit_id"]
    assert ask.json["citations"] and missing.json["citations"] == []
    connection = db.connect(app.config["DATABASE_PATH"])
    audits = {
        row["audit_id"]: row
        for row in connection.execute(
            "SELECT audit_id, operation, status, skill_decisions_json FROM assistant_audit_operations"
        )
    }
    assert audits[search.json["audit_id"]]["status"] == "complete"
    assert audits[ask.json["audit_id"]]["status"] == "complete"
    assert audits[missing.json["audit_id"]]["status"] == "no-evidence"
    ask_hits = connection.execute(
        "SELECT citation_index, chunk_id FROM assistant_audit_hits WHERE audit_id = ?",
        (ask.json["audit_id"],),
    ).fetchall()
    assert ask_hits and ask_hits[0]["citation_index"] == ask.json["citations"][0]["index"]
    operation_columns = {row["name"] for row in connection.execute("PRAGMA table_info(assistant_audit_operations)")}
    hit_columns = {row["name"] for row in connection.execute("PRAGMA table_info(assistant_audit_hits)")}
    assert not ({"question", "answer", "prompt", "token", "api_key", "chunk_text"} & operation_columns)
    assert not ({"question", "answer", "prompt", "token", "api_key", "chunk_text"} & hit_columns)
    assert json.loads(audits[ask.json["audit_id"]]["skill_decisions_json"])
    connection.close()


def test_conversation_sse_audit_id_citations_and_skill_snapshot(app, client):
    _seed(app)
    provider = AuditAnswerProvider()
    app.extensions["answer_provider"] = provider
    student = _login(client, "student_a1", "student_a1_pass")
    conversation = client.post("/api/conversations", headers=student, json={}).json["conversation"]

    response = client.post(
        f"/api/conversations/{conversation['id']}/messages/stream",
        headers=student,
        json={"question": "一次函数"},
    )
    events = [
        (part.split("\n", 1)[0].removeprefix("event: "), json.loads(part.split("data: ", 1)[1]))
        for part in response.get_data(as_text=True).strip().split("\n\n")
    ]
    start = events[0][1]
    done = events[-1][1]
    assert response.status_code == 200
    assert start["audit_id"] == done["audit_id"]
    assert provider.calls[0]["skill_instruction"]
    connection = db.connect(app.config["DATABASE_PATH"])
    audit = db.list_audit_operations(connection, {"audit_id": done["audit_id"]}, limit=1, offset=0)[0]
    assert audit["status"] == "complete" and audit["hits"][0]["citation_index"] == 1
    original_setting_version = audit["skill_decisions"][0]["class_setting_version"]
    original_package_version = audit["skill_decisions"][0]["package_version"]
    db.update_assistant_skill(connection, 1, False, "solution-guidance")
    connection.close()
    app.extensions["skill_registry"]["solution-guidance"]["version"] = "9.9.9"
    detail = client.get(f"/api/conversations/{conversation['id']}", headers=student).json
    assistant_message = detail["messages"][-1]
    assert assistant_message["skill_snapshot"]["class_setting_version"] == original_setting_version
    assert assistant_message["skill_snapshot"]["selected_skills"][0]["package_version"] == original_package_version
    assert assistant_message["skill_snapshot"]["selected_skills"][0]["package_version"] == "1.0.0"


def test_provider_failures_are_audited_and_do_not_leak_diagnostics(app, client):
    _seed(app)
    app.extensions["answer_provider"] = FailedAuditAnswerProvider()
    student = _login(client, "student_a1", "student_a1_pass")
    response = client.post("/api/ask", headers=student, json={"question": "一次函数"})
    assert response.status_code == 503
    assert response.json["audit_id"]
    assert "secret diagnostic" not in response.get_data(as_text=True)

    conversation = client.post("/api/conversations", headers=student, json={}).json["conversation"]
    stream = client.post(
        f"/api/conversations/{conversation['id']}/messages/stream",
        headers=student,
        json={"question": "一次函数"},
    )
    events = [
        (part.split("\n", 1)[0].removeprefix("event: "), json.loads(part.split("data: ", 1)[1]))
        for part in stream.get_data(as_text=True).strip().split("\n\n")
    ]
    error = next(payload for name, payload in events if name == "error")
    assert error["audit_id"]
    assert "secret diagnostic" not in stream.get_data(as_text=True)
    connection = db.connect(app.config["DATABASE_PATH"])
    statuses = {
        row["audit_id"]: row["status"]
        for row in connection.execute(
            "SELECT audit_id, status FROM assistant_audit_operations WHERE audit_id IN (?, ?)",
            (response.json["audit_id"], error["audit_id"]),
        )
    }
    assert statuses == {
        response.json["audit_id"]: "failed",
        error["audit_id"]: "failed",
    }
    connection.close()


def test_admin_audit_access_requires_local_cli_grant_and_bounds_pagination(app, client):
    _seed(app)
    student = _login(client, "student_a1", "student_a1_pass")
    teacher = _login(client, "teacher_a", "teacher_a_pass")
    client.get("/api/knowledge/search?q=一次函数&mode=keyword", headers=student)
    assert client.get("/api/admin/audits?audit_id=known-or-not", headers=teacher).status_code == 403
    assert client.get("/api/admin/audits?audit_id=known-or-not", headers=student).status_code == 403
    assert client.post("/api/admin/audits/grant", headers=teacher, json={"role": "admin"}).status_code == 404

    root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment["DATABASE_PATH"] = app.config["DATABASE_PATH"]
    environment["PYTHONPATH"] = str(root)
    subprocess.run(
        [sys.executable, str(root / "scripts" / "admin_access.py"), "grant", "teacher_a", "--granted-by", "pytest"],
        cwd=root,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )

    result = client.get("/api/admin/audits?operation=search&limit=1&offset=0", headers=teacher)
    assert result.status_code == 200 and result.json["audits"]
    assert result.json["limit"] == 1
    assert client.get("/api/admin/audits?limit=101", headers=teacher).status_code == 400
    assert client.get("/api/admin/audits?offset=100001", headers=teacher).status_code == 400
    record = result.json["audits"][0]
    assert record["audit_id"] and "hits" in record
    assert all("chunk_text" not in hit and "answer" not in hit for hit in record["hits"])
    audit_id = record["audit_id"]
    assert client.get(f"/api/admin/audits?audit_id={audit_id}", headers=teacher).json["audits"][0]["audit_id"] == audit_id
    assert client.get("/api/admin/audits?class_id=1&user_id=2&skill_key=solution-guidance", headers=teacher).status_code == 200
    assert client.get("/api/admin/audits?material_id=1&chunk_id=1", headers=teacher).status_code == 200
    assert client.get("/api/admin/audits?created_after=2000-01-01&created_before=2999-12-31", headers=teacher).status_code == 200

    subprocess.run(
        [sys.executable, str(root / "scripts" / "admin_access.py"), "revoke", "teacher_a"],
        cwd=root,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    assert client.get(f"/api/admin/audits?audit_id={audit_id}", headers=teacher).status_code == 403


def test_search_retrieval_failure_is_saved_as_failed_audit(app, client):
    _seed(app)
    student = _login(client, "student_a1", "student_a1_pass")
    from unittest.mock import patch
    from app.retrieval import RetrievalUnavailable

    with patch("app.retrieval_routes.retrieval.search", side_effect=RetrievalUnavailable("unavailable")):
        response = client.get("/api/knowledge/search?q=一次函数", headers=student)
    assert response.status_code == 503
    connection = db.connect(app.config["DATABASE_PATH"])
    row = connection.execute(
        "SELECT status, operation FROM assistant_audit_operations ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    assert tuple(row) == ("failed", "search")
    connection.close()
