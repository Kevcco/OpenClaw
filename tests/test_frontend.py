def login(client, username, password):
    response = client.post("/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json['access_token']}"}


def test_workspace_loads_assets_and_uses_server_identity(client, app):
    from app import db

    connection = db.connect(app.config["DATABASE_PATH"])
    db.init_schema(connection)
    db.seed_data(connection, app.config["UPLOAD_DIR"])
    connection.close()
    headers = login(client, "teacher_a", "teacher_a_pass")

    page = client.get("/materials")
    script = client.get("/static/workspace.js")
    login_script = client.get("/static/login.js")
    stylesheet = client.get("/static/app.css")
    assistant_settings_stylesheet = client.get("/static/assistant-settings.css")

    assert page.status_code == 200
    assert b"data-upload-panel" in page.data
    assert b"/api/me" in script.data
    assert b"Authorization" in script.data
    assert b"sessionStorage" in script.data
    assert b'credentials: "same-origin"' not in script.data
    assert b'credentials: "omit"' in script.data
    assert b'sessionStorage.removeItem(tokenStorageKey)' in script.data
    assert b'window.location.assign("/login")' in script.data
    assert b"/api/materials/upload" in script.data
    assert b"/api/materials" in script.data
    assert b"textContent = material.body_text" in script.data
    assert b"/api/knowledge/search" in script.data
    assert b"/api/ask" in script.data
    assert b"const askKnowledge" in script.data
    assert b'if (mode === "hybrid") await askWithEvidence(query)' not in script.data
    assert b"textContent = hit.snippet" in script.data
    assert b"data-knowledge-search" in page.data
    assert b"data-knowledge-ask" in page.data
    assert b"data-knowledge-ask-submit" in page.data
    assert b"data-answer-status" in page.data
    assert b"data-answer-panel" in page.data
    assert b"data-assistant-workspace" in page.data
    assert b"data-conversation-list" in page.data
    assert b"data-conversation-messages" in page.data
    assert b"data-new-conversation" in page.data
    assert b"data-assistant-settings hidden" in page.data
    assert "技能配置".encode("utf-8") in page.data
    assert b"data-assistant-skill-list" in page.data
    assert "提示词配置".encode("utf-8") in page.data
    assert "A班材料" not in page.get_data(as_text=True)
    assert b"/api/conversations?limit=100" in script.data
    assert b"/messages/stream" in script.data
    assert b"text/event-stream" in script.data
    assert b"Authorization: `Bearer ${token}`" in script.data
    assert b"textContent += payload.text" in script.data
    assert b"addMessageCitations" in script.data
    assert b"credentials: \"omit\"" in script.data
    assert b"teacherSettings.hidden = false" in script.data
    assert b"teacherSettings.open = true" in script.data
    assert b"/api/assistant/settings" in script.data
    assert b"/api/assistant/skills" in script.data
    assert b"encodeURIComponent(skillKey)" in script.data
    assert b"innerHTML" not in script.data
    assert stylesheet.status_code == 200
    assert assistant_settings_stylesheet.status_code == 200
    assert b"sessionStorage.setItem" in login_script.data
    assert b'credentials: "omit"' in login_script.data
    assert b"Authorization" in login_script.data or b"access_token" in login_script.data
    assert b"document.cookie" not in login_script.data


def test_student_cannot_use_upload_even_with_workspace_script(client, app):
    from app import db

    connection = db.connect(app.config["DATABASE_PATH"])
    db.init_schema(connection)
    db.seed_data(connection, app.config["UPLOAD_DIR"])
    connection.close()
    headers = login(client, "student_a1", "student_a1_pass")

    assert client.get("/api/me", headers=headers).json["role"] == "student"
    assert client.post("/api/materials/upload", headers=headers).status_code == 403
