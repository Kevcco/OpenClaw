from support import ACCOUNTS, login, request, row


def run():
    token, _ = login("student_a")
    username = ACCOUNTS["student_a"][0]
    user = row("SELECT id, class_id FROM users WHERE username = ?", (username,))
    created = request(
        "POST", "/api/conversations", token=token, payload={"title": "API 合约测试会话"}
    )
    assert created["status"] == 201
    conversation = created["json"]["conversation"]
    stored = row(
        "SELECT id, owner_user_id, class_id, title FROM conversations WHERE id = ?",
        (conversation["id"],),
    )
    assert stored is not None
    assert stored["owner_user_id"] == user["id"]
    assert stored["class_id"] == user["class_id"]
    assert stored["title"] == conversation["title"] == "API 合约测试会话"
    listed = request("GET", "/api/conversations?limit=100", token=token)
    assert listed["status"] == 200
    assert any(item["id"] == conversation["id"] for item in listed["json"]["conversations"])
    assert request("DELETE", f"/api/conversations/{conversation['id']}", token=token)["status"] == 200
    assert row("SELECT id FROM conversations WHERE id = ?", (conversation["id"],)) is None
    return f"Created and listed owner/class-isolated conversation id={conversation['id']}"
