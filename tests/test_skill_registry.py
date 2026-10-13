import json
from pathlib import Path

import pytest

from app import db
from app.answer import ExtractiveAnswerProvider
from app.skill_registry import SkillPackageError, load_registry, select_skills
from app.vector_store import HashEmbeddingProvider, InMemoryVectorStore


def _package(root, folder, metadata, instruction="完整技能指令"):
    directory = root / folder
    directory.mkdir(parents=True)
    (directory / "skill.yaml").write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
    (directory / "instructions.md").write_text(instruction, encoding="utf-8")
    return directory


def _metadata(key="test-skill", **overrides):
    metadata = {
        "key": key,
        "name": "测试技能",
        "version": "1.0.0",
        "summary": "测试技能简介",
        "applicability": {"any_terms": ["错误", "解题"]},
        "priority": 10,
        "instruction_file": "instructions.md",
        "instruction_tokens": 12,
    }
    metadata.update(overrides)
    return metadata


def test_registry_rejects_missing_duplicate_and_traversal_metadata(tmp_path):
    root = tmp_path / "skills"
    root.mkdir()
    _package(root, "valid", _metadata())
    _package(root, "duplicate-id", _metadata("test-skill"))
    _package(root, "missing", {"key": "missing-fields"})
    traversal = _package(root, "traversal", _metadata("traversal"))
    (traversal / "skill.yaml").write_text(
        json.dumps(_metadata("traversal", instruction_file="../outside.md")), encoding="utf-8"
    )
    duplicate = _package(root, "duplicate", _metadata("duplicate"))
    (duplicate / "skill.yaml").write_text(
        '{"key":"duplicate","key":"overridden","name":"n","version":"1",'
        '"summary":"s","applicability":{"any_terms":["x"]},"priority":1,'
        '"instruction_file":"instructions.md","instruction_tokens":1}',
        encoding="utf-8",
    )

    registry = load_registry(root)

    assert list(registry) == ["test-skill"]
    assert registry["test-skill"]["instruction"] == "完整技能指令"


def test_builtin_packages_have_unique_keys_and_declared_costs():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "skills"
    registry = load_registry(root)
    assert set(registry) == {"solution-guidance", "error-explanation", "homework-review"}
    assert len({package["key"] for package in registry.values()}) == 3
    assert all(package["instruction_tokens"] > 0 for package in registry.values())


def test_selection_is_deterministic_budgeted_and_does_not_execute_scripts(tmp_path):
    root = tmp_path / "skills"
    root.mkdir()
    script_marker = tmp_path / "script-executed"
    scripts = root / "solution" / "scripts"
    _package(root, "solution", _metadata("solution", priority=20, instruction_tokens=8))
    scripts.mkdir()
    (scripts / "malicious.py").write_text(
        f"from pathlib import Path; Path({str(script_marker)!r}).touch()", encoding="utf-8"
    )
    _package(root, "error", _metadata("error", priority=10, instruction_tokens=8))
    registry = load_registry(root)
    settings = [
        {"skill_key": key, "enabled": True, "version": 2}
        for key in registry
    ]

    selection = select_skills(registry, settings, "这道错题怎么解题", 10, settings_version=7)

    assert [package["key"] for package in selection["selected"]] == ["solution"]
    assert "完整技能指令" in selection["instruction"]
    assert sum(
        decision["instruction_tokens"]
        for decision in selection["decisions"]
        if decision["decision"] == "selected"
    ) <= 10
    assert {item["decision"] for item in selection["decisions"]} == {"selected", "budget-skipped"}
    assert all(item["candidate"] and item["matched"] for item in selection["decisions"])
    selected_by_key = {item["skill_key"]: item["selected"] for item in selection["decisions"]}
    assert selected_by_key == {"error": False, "solution": True}
    assert selection["snapshot"]["class_setting_version"] == 7
    assert not script_marker.exists()


@pytest.mark.parametrize(
    ("enabled", "question", "budget", "expected"),
    [
        (False, "这道题的解题步骤", 20, "disabled"),
        (True, "天气怎么样", 20, "unmatched"),
        (True, "这道题的解题步骤", 20, "selected"),
        (True, "这道题的解题步骤", 1, "budget-skipped"),
    ],
)
def test_matching_reports_candidate_match_and_budget_decisions(tmp_path, enabled, question, budget, expected):
    root = tmp_path / "skills"
    root.mkdir()
    _package(root, "test", _metadata())
    registry = load_registry(root)
    result = select_skills(
        registry,
        [{"skill_key": "test-skill", "enabled": enabled, "version": 1}],
        question,
        budget,
    )
    decision = result["decisions"][0]
    assert decision["decision"] == expected
    assert decision["candidate"] is enabled
    assert decision["matched"] is (enabled and "解题" in question)
    assert decision["selected"] is (expected == "selected")


def test_equal_priority_uses_stable_key_order(tmp_path):
    root = tmp_path / "skills"
    root.mkdir()
    _package(root, "zeta", _metadata("zeta", priority=5, instruction_tokens=5))
    _package(root, "alpha", _metadata("alpha", priority=5, instruction_tokens=5))
    registry = load_registry(root)
    settings = [
        {"skill_key": key, "enabled": True, "version": 1}
        for key in registry
    ]
    selected = select_skills(registry, settings, "解题", 5)
    assert [package["key"] for package in selected["selected"]] == ["alpha"]


def test_summaries_alone_do_not_activate_extractive_guidance():
    registry = load_registry(Path(__file__).resolve().parents[1] / "skills")
    settings = [
        {"skill_key": key, "enabled": key == "solution-guidance", "version": 1}
        for key in registry
    ]
    selection = select_skills(registry, settings, "平均数的含义", 800)
    assert selection["instruction"] and not selection["selected"]
    answer = ExtractiveAnswerProvider().answer(
        "平均数", [{"title": "数学材料", "chunk_index": 0, "chunk_text": "平均数是总和除以数量"}],
        skill_instruction=selection["instruction"],
    )
    assert answer.startswith("根据本班材料")


def test_legacy_seed_preserves_solution_toggle_and_reconciles_new_skills(app):
    connection = db.connect(app.config["DATABASE_PATH"])
    db.init_schema(connection)
    db.seed_data(connection, app.config["UPLOAD_DIR"])
    db.update_assistant_skill(connection, 1, False, "solution-guidance")
    db.update_assistant_skill(connection, 2, True, "solution-guidance")
    old_rows = {
        row["skill_key"]: (row["enabled"], row["version"])
        for row in db.list_assistant_skills(connection, 1)
    }
    setting_version = db.get_assistant_skill_settings_version(connection, 1)
    b_version = db.get_assistant_skill_settings_version(connection, 2)
    db.seed_data(connection, app.config["UPLOAD_DIR"])
    db.init_schema(connection)
    new_rows = {
        row["skill_key"]: (row["enabled"], row["version"])
        for row in db.list_assistant_skills(connection, 1)
    }
    assert new_rows == old_rows
    assert new_rows["solution-guidance"] == old_rows["solution-guidance"]
    assert new_rows["error-explanation"][0] == 0
    assert new_rows["homework-review"][0] == 0
    assert db.get_assistant_skill_settings_version(connection, 1) == setting_version
    assert db.get_assistant_skill_settings_version(connection, 2) == b_version
    assert db.get_assistant_skill(connection, 2, "solution-guidance")["enabled"] == 1
    assert connection.execute(
        "SELECT count(*) FROM assistant_skills WHERE class_id = 1"
    ).fetchone()[0] == 3
    connection.close()


def test_teacher_general_skill_controls_and_students_are_denied(app, client):
    connection = db.connect(app.config["DATABASE_PATH"])
    db.init_schema(connection)
    db.seed_data(connection, app.config["UPLOAD_DIR"])
    connection.close()
    app.extensions["knowledge_embedding_provider"] = HashEmbeddingProvider()
    app.extensions["knowledge_vector_store"] = InMemoryVectorStore()
    teacher_login = client.post("/api/login", json={"username": "teacher_a", "password": "teacher_a_pass"})
    student_login = client.post("/api/login", json={"username": "student_a1", "password": "student_a1_pass"})
    teacher = {"Authorization": f"Bearer {teacher_login.json['access_token']}"}
    student = {"Authorization": f"Bearer {student_login.json['access_token']}"}

    listed = client.get("/api/assistant/skills", headers=teacher)
    assert listed.status_code == 200
    assert {skill["key"] for skill in listed.json["skills"]} == {
        "solution-guidance", "error-explanation", "homework-review"
    }
    before = client.get("/api/assistant/skills", headers=student)
    assert before.status_code == 403
    updated = client.patch(
        "/api/assistant/skills/error-explanation",
        headers=teacher,
        json={"enabled": True, "class_id": 2, "instruction": "forged"},
    )
    assert updated.status_code == 200 and updated.json["enabled"] is True
    denied = client.patch(
        "/api/assistant/skills/homework-review", headers=student, json={"enabled": True}
    )
    assert denied.status_code == 403
    connection = db.connect(app.config["DATABASE_PATH"])
    assert db.get_assistant_skill(connection, 2, "error-explanation")["enabled"] == 0
    assert db.get_assistant_skill(connection, 1, "error-explanation")["instruction"].startswith("先复述")
    connection.close()
