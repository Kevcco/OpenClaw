from support import ACCOUNTS, login, request, row


def run():
    teacher, _ = login("teacher_a")
    student, _ = login("student_a")
    user = row("SELECT class_id FROM users WHERE username = ?", (ACCOUNTS["teacher_a"][0],))
    before = row(
        "SELECT enabled, version FROM assistant_skills WHERE class_id = ? AND skill_key = ?",
        (user["class_id"], "error-explanation"),
    )
    enabled = request(
        "PATCH",
        "/api/assistant/skills/error-explanation",
        token=teacher,
        payload={"enabled": True, "class_id": 2, "instruction": "forged"},
    )
    denied = request(
        "PATCH",
        "/api/assistant/skills/homework-review",
        token=student,
        payload={"enabled": True},
    )
    saved = row(
        "SELECT enabled, version FROM assistant_skills WHERE class_id = ? AND skill_key = ?",
        (user["class_id"], "error-explanation"),
    )
    class_b = row("SELECT id FROM classes WHERE name = ?", ("B班",))
    b_skill = row(
        "SELECT enabled FROM assistant_skills WHERE class_id = ? AND skill_key = ?",
        (class_b["id"], "error-explanation"),
    )
    assert enabled["status"] == 200 and denied["status"] == 403
    assert enabled["json"]["enabled"] is True
    assert saved["enabled"] == 1 and saved["version"] > before["version"]
    assert b_skill["enabled"] == 0
    request(
        "PATCH",
        "/api/assistant/skills/error-explanation",
        token=teacher,
        payload={"enabled": bool(before["enabled"])},
    )
    return "Generic toggle is class-scoped and ignores forged instruction/class fields"
