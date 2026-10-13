import re


def _actual_operations(app):
    operations = set()
    for rule in app.url_map.iter_rules():
        path = re.sub(r"<(?:[^:<>]+:)?([^<>]+)>", r"{\1}", rule.rule)
        for method in rule.methods - {"HEAD", "OPTIONS"}:
            operations.add((path, method.lower()))
    return operations


def test_openapi_covers_required_routes_and_bearer_boundaries(app):
    from app.openapi_docs import openapi_document

    document = openapi_document()
    paths = document["paths"]
    actual = _actual_operations(app)
    required = {
        ("/health", "get"),
        ("/login", "post"),
        ("/api/login", "post"),
        ("/logout", "post"),
        ("/api/me", "get"),
        ("/api/knowledge/search", "get"),
        ("/api/ask", "post"),
        ("/api/assistant/settings", "get"),
        ("/api/assistant/settings", "put"),
        ("/api/assistant/skills/solution-guidance", "get"),
        ("/api/assistant/skills/solution-guidance", "patch"),
        ("/api/assistant/skills", "get"),
        ("/api/assistant/skills/{skill_key}", "patch"),
        ("/api/admin/audits", "get"),
        ("/api/conversations", "get"),
        ("/api/conversations", "post"),
        ("/api/conversations/{conversation_id}", "get"),
        ("/api/conversations/{conversation_id}", "delete"),
        ("/api/conversations/{conversation_id}/messages/stream", "post"),
    }
    documented = {
        (path, method)
        for path, item in paths.items()
        for method in item
        if method in {"get", "post", "put", "patch", "delete"}
    }

    assert document["openapi"].startswith("3.")
    assert required <= documented
    assert documented <= actual
    assert document["components"]["securitySchemes"]["BearerAuth"] == {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "Opaque access token",
    }
    assert paths["/health"]["get"]["security"] == []
    assert paths["/login"]["post"]["security"] == []
    for path, item in paths.items():
        for method, operation in item.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            if (path, method) not in {("/health", "get"), ("/login", "post"), ("/api/login", "post")}:
                assert operation["security"] == [{"BearerAuth": []}]
    stream_response = paths["/api/conversations/{conversation_id}/messages/stream"]["post"]["responses"]["200"]
    assert "text/event-stream" in stream_response["content"]
    assert "401" in paths["/api/me"]["get"]["responses"]
    assert "403" in paths["/api/assistant/settings"]["put"]["responses"]
    assert "404" in paths["/api/conversations/{conversation_id}"]["get"]["responses"]
    assert "audit_id" in paths["/api/knowledge/search"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["properties"]
    assert "audit_id" in paths["/api/ask"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]["properties"]
    assert paths["/api/admin/audits"]["get"]["parameters"][-2]["schema"]["maximum"] == 100


def test_openapi_json_and_interactive_swagger_page_are_available(client):
    document = client.get("/openapi.json")
    page = client.get("/swagger/")

    assert document.status_code == 200
    assert document.is_json
    assert "/api/conversations/{conversation_id}/messages/stream" in document.json["paths"]
    assert page.status_code == 200
    assert b"Bearer Token" in page.data
    assert b"/openapi.json" in page.data
