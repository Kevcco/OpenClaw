from support import ACCOUNTS, login, request, row


def run():
    teacher, _ = login("teacher_a")
    student, _ = login("student_a")
    user = row("SELECT class_id FROM users WHERE username = ?", (ACCOUNTS["teacher_a"][0],))
    before = row(
        "SELECT enabled, version FROM assistant_skills WHERE class_id = ? AND skill_key = ?",
        (user["class_id"], "solution-guidance"),
    )
    saved = request(
        "PATCH",
        "/api/assistant/skills/solution-guidance",
        token=teacher,
        payload={"enabled": bool(before["enabled"])},
    )
    denied = request(
        "PATCH",
        "/api/assistant/skills/solution-guidance",
        token=student,
        payload={"enabled": not bool(before["enabled"]), "instruction": "forbidden"},
    )
    after = row(
        "SELECT enabled, version FROM assistant_skills WHERE class_id = ? AND skill_key = ?",
        (user["class_id"], "solution-guidance"),
    )
    assert saved["status"] == 200 and denied["status"] == 403
    assert after["enabled"] == before["enabled"] == int(saved["json"]["enabled"])
    assert after["version"] == before["version"] + 1 == saved["json"]["version"]
    return "Teacher setting version is persisted; student cannot change the skill or its instruction"
