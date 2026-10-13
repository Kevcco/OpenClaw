from support import ACCOUNTS, login, request, row


def run():
    teacher, _ = login("teacher_a")
    student, _ = login("student_a")
    result = request("GET", "/api/assistant/settings", token=teacher)
    denied = request("GET", "/api/assistant/settings", token=student)
    assert result["status"] == 200 and denied["status"] == 403
    user = row("SELECT class_id FROM users WHERE username = ?", (ACCOUNTS["teacher_a"][0],))
    stored = row("SELECT prompt, prompt_version FROM assistant_configs WHERE class_id = ?", (user["class_id"],))
    assert stored is not None
    assert result["json"]["prompt"] == stored["prompt"]
    assert result["json"]["prompt_version"] == stored["prompt_version"]
    assert "token_hash" not in result["json"] and "api_key" not in result["json"]
    return "Teacher prompt response matches this class's SQLite configuration; student receives 403"
