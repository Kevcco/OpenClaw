from support import ACCOUNTS, login, request, row


def run():
    teacher, _ = login("teacher_a")
    student, _ = login("student_a")
    user = row("SELECT class_id FROM users WHERE username = ?", (ACCOUNTS["teacher_a"][0],))
    result = request("GET", "/api/assistant/skills", token=teacher)
    denied = request("GET", "/api/assistant/skills", token=student)
    assert result["status"] == 200 and denied["status"] == 403
    skills = {skill["key"]: skill for skill in result["json"]["skills"]}
    assert set(skills) == {"solution-guidance", "error-explanation", "homework-review"}
    assert skills["solution-guidance"]["enabled"] is bool(
        row(
            "SELECT enabled FROM assistant_skills WHERE class_id = ? AND skill_key = ?",
            (user["class_id"], "solution-guidance"),
        )["enabled"]
    )
    return "Teacher registry lists all three package-backed skills; students receive 403"
