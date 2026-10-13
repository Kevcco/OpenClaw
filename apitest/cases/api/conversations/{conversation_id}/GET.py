from support import ACCOUNTS, login, request, row


def run():
    token_a, _ = login("student_a")
    token_b, _ = login("student_b")
    created = request("POST", "/api/conversations", token=token_a, payload={"title": "隔离测试"})
    assert created["status"] == 201
    conversation_id = created["json"]["conversation"]["id"]
    path = f"/api/conversations/{conversation_id}"
    owner_read = request("GET", path, token=token_a)
    other_read = request("GET", path, token=token_b)
    other_delete = request("DELETE", path, token=token_b)
    assert owner_read["status"] == 200
    assert owner_read["json"]["conversation"]["id"] == conversation_id
    assert other_read["status"] == other_delete["status"] == 404
    owner = row("SELECT id, class_id FROM users WHERE username = ?", (ACCOUNTS["student_a"][0],))
    stored = row("SELECT owner_user_id, class_id FROM conversations WHERE id = ?", (conversation_id,))
    assert stored["owner_user_id"] == owner["id"]
    assert stored["class_id"] == owner["class_id"]
    assert "title" not in other_read["json"]
    assert request("DELETE", path, token=token_a)["status"] == 200
    assert row("SELECT id FROM conversations WHERE id = ?", (conversation_id,)) is None
    return "Owner can read/delete; another class receives opaque 404 and cannot delete"
