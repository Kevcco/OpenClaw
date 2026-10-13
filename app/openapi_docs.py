"""OpenAPI document and local interactive API documentation routes."""

from flask import Blueprint, jsonify, render_template


bp = Blueprint("api_docs", __name__)


def _json_request(description, schema, example):
    return {
        "required": True,
        "description": description,
        "content": {
            "application/json": {
                "schema": schema,
                "example": example,
            }
        },
    }


def _responses(*, success="Successful response", success_schema=None, success_code="200"):
    content = {"description": success}
    if success_schema:
        content["content"] = {"application/json": {"schema": success_schema}}
    result = {success_code: content}
    result.update(
        {
            "400": {"description": "Invalid request"},
            "401": {"description": "Missing, expired, or revoked Bearer token"},
            "403": {"description": "Authenticated user lacks the required role"},
            "404": {"description": "Resource not found or not visible to this user"},
            "503": {"description": "Retrieval or answer service unavailable"},
        }
    )
    return result


def openapi_document():
    bearer = [{"BearerAuth": []}]
    json_schema = {"type": "object", "additionalProperties": True}
    error_schema = {
        "type": "object",
        "properties": {"error": {"type": "string"}},
        "required": ["error"],
    }
    login_path = {
        "post": {
            "tags": ["Authentication"],
            "summary": "Login and receive an opaque Bearer token",
            "security": [],
            "requestBody": _json_request(
                "Demo account credentials",
                {"$ref": "#/components/schemas/LoginRequest"},
                {"username": "student_a1", "password": "student_a1_pass"},
            ),
            "responses": {
                "200": {
                    "description": "Bearer token and identity",
                    "content": {"application/json": {"schema": {"$ref": "#/components/schemas/LoginResponse"}}},
                },
                "400": {"description": "JSON credentials required"},
                "401": {"description": "Invalid credentials"},
            },
        }
    }
    protected_json = _responses(success_schema=json_schema)
    protected_no_body = _responses(success="Request completed")
    prompt_request = _json_request(
        "Prompt text is limited to 6000 characters",
        {"$ref": "#/components/schemas/PromptUpdate"},
        {"prompt": "你是耐心的数学学习助手，请用简明中文回答。"},
    )
    conversation_request = _json_request(
        "Optional conversation title",
        {"$ref": "#/components/schemas/ConversationCreate"},
        {"title": "一次函数复习"},
    )
    message_request = _json_request(
        "Question to send. Client-supplied class, prompt, and skill values are ignored.",
        {"$ref": "#/components/schemas/MessageRequest"},
        {"question": "一次函数是什么？"},
    )
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "CampusClaw API",
            "version": "1.0.0",
            "description": (
                "课堂教学知识库与解题助手 API。登录后将 access_token 作为 "
                "Authorization: Bearer <token> 请求头发送。浏览器页面不接受 Cookie 或 URL Token。"
            ),
        },
        "servers": [{"url": "/", "description": "当前服务"}],
        "tags": [
            {"name": "Authentication"},
            {"name": "Knowledge"},
            {"name": "Assistant settings"},
            {"name": "Conversations"},
        ],
        "paths": {
            "/health": {
                "get": {
                    "tags": ["Authentication"],
                    "summary": "Public health check",
                    "security": [],
                    "responses": {"200": {"description": "Service is healthy"}},
                }
            },
            "/login": login_path,
            "/api/login": login_path,
            "/logout": {
                "post": {
                    "tags": ["Authentication"],
                    "summary": "Revoke current Bearer token",
                    "security": bearer,
                    "responses": protected_no_body,
                }
            },
            "/api/me": {
                "get": {
                    "tags": ["Authentication"],
                    "summary": "Get current identity and class from Bearer token",
                    "security": bearer,
                    "responses": protected_json,
                }
            },
            "/api/knowledge/search": {
                "get": {
                    "tags": ["Knowledge"],
                    "summary": "Search only the authenticated user's class",
                    "security": bearer,
                    "parameters": [
                        {"name": "q", "in": "query", "required": True, "schema": {"type": "string"}},
                        {"name": "mode", "in": "query", "schema": {"type": "string", "enum": ["keyword", "vector", "hybrid"], "default": "hybrid"}},
                        {"name": "limit", "in": "query", "schema": {"type": "integer", "minimum": 1, "maximum": 20, "default": 10}},
                    ],
                    "responses": protected_json,
                }
            },
            "/api/ask": {
                "post": {
                    "tags": ["Knowledge"],
                    "summary": "Single-turn grounded answer (compatibility endpoint)",
                    "security": bearer,
                    "requestBody": _json_request("Question and optional user/assistant history", {"$ref": "#/components/schemas/AskRequest"}, {"question": "一次函数是什么？", "history": []}),
                    "responses": protected_json,
                }
            },
            "/api/assistant/settings": {
                "get": {
                    "tags": ["Assistant settings"],
                    "summary": "Read this class's assistant prompt (teacher only)",
                    "security": bearer,
                    "responses": protected_json,
                },
                "put": {
                    "tags": ["Assistant settings"],
                    "summary": "Update this class's assistant prompt (teacher only)",
                    "security": bearer,
                    "requestBody": prompt_request,
                    "responses": protected_json,
                },
            },
            "/api/assistant/skills/solution-guidance": {
                "get": {
                    "tags": ["Assistant settings"],
                    "summary": "Read solution-guidance skill settings (teacher only)",
                    "security": bearer,
                    "responses": protected_json,
                },
                "patch": {
                    "tags": ["Assistant settings"],
                    "summary": "Enable or disable solution-guidance (teacher only)",
                    "security": bearer,
                    "requestBody": _json_request("Only the enabled flag can be changed", {"$ref": "#/components/schemas/SkillUpdate"}, {"enabled": True}),
                    "responses": protected_json,
                },
            },
            "/api/conversations": {
                "get": {
                    "tags": ["Conversations"],
                    "summary": "List the authenticated user's conversations",
                    "security": bearer,
                    "parameters": [{"name": "limit", "in": "query", "schema": {"type": "integer", "minimum": 1, "maximum": 100, "default": 50}}],
                    "responses": protected_json,
                },
                "post": {
                    "tags": ["Conversations"],
                    "summary": "Create a conversation owned by the authenticated user",
                    "security": bearer,
                    "requestBody": conversation_request,
                    "responses": _responses(success="Conversation created", success_schema=json_schema, success_code="201"),
                },
            },
            "/api/conversations/{conversation_id}": {
                "parameters": [{"name": "conversation_id", "in": "path", "required": True, "schema": {"type": "integer"}}],
                "get": {
                    "tags": ["Conversations"],
                    "summary": "Read this user's conversation and messages",
                    "security": bearer,
                    "responses": protected_json,
                },
                "delete": {
                    "tags": ["Conversations"],
                    "summary": "Delete this user's conversation",
                    "security": bearer,
                    "responses": protected_json,
                },
            },
            "/api/conversations/{conversation_id}/messages/stream": {
                "post": {
                    "tags": ["Conversations"],
                    "summary": "Send a question and receive SSE events",
                    "description": "SSE event order: start, one or more delta events, then done; or error. The done data contains message_id, final answer, and citations. Include Bearer token in Authorization header.",
                    "security": bearer,
                    "parameters": [{"name": "conversation_id", "in": "path", "required": True, "schema": {"type": "integer"}}],
                    "requestBody": message_request,
                    "responses": {
                        "200": {"description": "Server-sent events", "content": {"text/event-stream": {"schema": {"type": "string"}, "example": "event: start\\ndata: {\\\"message_id\\\":12}\\n\\nevent: delta\\ndata: {\\\"text\\\":\\\"先看题目条件\\\"}\\n\\nevent: done\\ndata: {\\\"message_id\\\":12,\\\"answer\\\":\\\"...\\\",\\\"citations\\\":[]}\\n\\n"}}},
                        "400": {"description": "Invalid question"},
                        "401": {"description": "Missing, expired, or revoked Bearer token"},
                        "404": {"description": "Conversation is not visible to this user"},
                        "503": {"description": "Assistant configuration unavailable"},
                    },
                }
            },
        },
        "components": {
            "securitySchemes": {
                "BearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "Opaque access token"}
            },
            "schemas": {
                "Error": error_schema,
                "LoginRequest": {
                    "type": "object",
                    "properties": {"username": {"type": "string"}, "password": {"type": "string", "format": "password"}},
                    "required": ["username", "password"],
                },
                "LoginResponse": {
                    "type": "object",
                    "properties": {
                        "access_token": {"type": "string"}, "token_type": {"type": "string", "const": "Bearer"},
                        "expires_in": {"type": "integer"}, "expires_at": {"type": "integer"}, "user_id": {"type": "integer"},
                        "username": {"type": "string"}, "role": {"type": "string", "enum": ["teacher", "student"]}, "class_id": {"type": "integer"},
                    },
                },
                "PromptUpdate": {"type": "object", "properties": {"prompt": {"type": "string", "minLength": 1, "maxLength": 6000}}, "required": ["prompt"]},
                "SkillUpdate": {"type": "object", "properties": {"enabled": {"type": "boolean"}}, "required": ["enabled"]},
                "AskRequest": {"type": "object", "properties": {"question": {"type": "string"}, "history": {"type": "array", "items": json_schema}}, "required": ["question"]},
                "ConversationCreate": {"type": "object", "properties": {"title": {"type": "string", "maxLength": 120}}},
                "MessageRequest": {"type": "object", "properties": {"question": {"type": "string", "minLength": 1, "maxLength": 4000}}, "required": ["question"]},
            },
        },
    }


@bp.get("/openapi.json")
def openapi_json():
    return jsonify(openapi_document())


@bp.get("/swagger")
@bp.get("/swagger/")
def swagger_ui():
    return render_template("swagger.html")
