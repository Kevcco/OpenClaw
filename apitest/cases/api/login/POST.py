from support import ACCOUNTS, login, request, row


def run():
    token, identity = login("student_a")
    username = ACCOUNTS["student_a"][0]
    user = row(
        "SELECT id, username, role, class_id FROM users WHERE username = ?",
        (username,),
    )
    assert user is not None
    assert identity["user_id"] == user["id"]
    assert identity["role"] == user["role"] == "student"
    assert identity["class_id"] == user["class_id"]
    me = request("GET", "/api/me", token=token)
    assert me["status"] == 200 and me["json"]["username"] == username
    stored = row(
        "SELECT count(*) AS amount FROM auth_tokens WHERE user_id = ? AND revoked_at IS NULL",
        (user["id"],),
    )
    assert stored["amount"] > 0
    return "Bearer login identity matches users and an active token row exists"
