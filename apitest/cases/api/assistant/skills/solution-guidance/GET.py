from support import ACCOUNTS, login, request, row


def run():
    teacher, _ = login("teacher_a")
    student, _ = login("student_a")
    result = request("GET", "/api/assistant/skills/solution-guidance", token=teacher)
    denied = request("GET", "/api/assistant/skills/solution-guidance", token=student)
    assert result["status"] == 200 and denied["status"] == 403
    user = row("SELECT class_id FROM users WHERE username = ?", (ACCOUNTS["teacher_a"][0],))
    stored = row(
        "SELECT skill_key, name, enabled, version FROM assistant_skills WHERE class_id = ? AND skill_key = ?",
        (user["class_id"], "solution-guidance"),
    )
    assert stored is not None
    assert result["json"]["key"] == stored["skill_key"]
    assert result["json"]["enabled"] is bool(stored["enabled"])
    assert result["json"]["version"] == stored["version"]
    return "Teacher skill response and enabled/version fields match SQLite; student receives 403"
