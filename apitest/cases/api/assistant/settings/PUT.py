from support import ACCOUNTS, login, request, row


def run():
    teacher, _ = login("teacher_a")
    student, _ = login("student_a")
    user = row("SELECT class_id FROM users WHERE username = ?", (ACCOUNTS["teacher_a"][0],))
    before = row("SELECT prompt, prompt_version FROM assistant_configs WHERE class_id = ?", (user["class_id"],))
    saved = request("PUT", "/api/assistant/settings", token=teacher, payload={"prompt": before["prompt"]})
    denied = request("PUT", "/api/assistant/settings", token=student, payload={"prompt": "student must not update"})
    after = row("SELECT prompt, prompt_version FROM assistant_configs WHERE class_id = ?", (user["class_id"],))
    assert saved["status"] == 200 and denied["status"] == 403
    assert after["prompt"] == before["prompt"] == saved["json"]["prompt"]
    assert after["prompt_version"] == before["prompt_version"] + 1 == saved["json"]["prompt_version"]
    return "Teacher update increments the saved prompt version; student update is rejected"
