"""Standard-library helpers shared by the URL-organized API checks."""

import json
import os
import sqlite3
import urllib.error
import urllib.request
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_URL = os.getenv("APITEST_BASE_URL", "http://127.0.0.1:8080").rstrip("/")
DATABASE_PATH = Path(
    os.getenv("APITEST_DATABASE_PATH", str(PROJECT_ROOT / "data" / "app.db"))
).expanduser()

ACCOUNTS = {
    "teacher_a": (
        os.getenv("APITEST_TEACHER_USERNAME", "teacher_a"),
        os.getenv("APITEST_TEACHER_PASSWORD", "teacher_a_pass"),
    ),
    "student_a": (
        os.getenv("APITEST_STUDENT_A_USERNAME", "student_a1"),
        os.getenv("APITEST_STUDENT_A_PASSWORD", "student_a1_pass"),
    ),
    "student_b": (
        os.getenv("APITEST_STUDENT_B_USERNAME", "student_b1"),
        os.getenv("APITEST_STUDENT_B_PASSWORD", "student_b1_pass"),
    ),
}
TOKEN_CACHE = {}


def request(method, path, *, token=None, payload=None, accept="application/json", timeout=45):
    headers = {"Accept": accept}
    body = None
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        f"{BASE_URL}{path}", data=body, headers=headers, method=method.upper()
    )
    try:
        response = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        raw = response.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            parsed = None
        return {
            "status": response.code,
            "headers": dict(response.headers.items()),
            "text": raw,
            "json": parsed,
        }


def login(account):
    if account in TOKEN_CACHE:
        token, identity = TOKEN_CACHE[account]
        return token, identity.copy()
    username, password = ACCOUNTS[account]
    result = request(
        "POST", "/api/login", payload={"username": username, "password": password}
    )
    assert result["status"] == 200, f"login failed for configured {account} account"
    payload = result["json"]
    assert isinstance(payload, dict) and isinstance(payload.get("access_token"), str)
    assert payload.get("token_type") == "Bearer"
    assert isinstance(payload.get("user_id"), int)
    TOKEN_CACHE[account] = (payload["access_token"], payload.copy())
    return payload["access_token"], payload


def logout_cached_tokens():
    results = []
    for account, (token, _identity) in list(TOKEN_CACHE.items()):
        result = request("POST", "/logout", token=token)
        results.append((account, result["status"]))
    TOKEN_CACHE.clear()
    return results


def database():
    if not DATABASE_PATH.is_file():
        raise RuntimeError(
            "SQLite file not found; set APITEST_DATABASE_PATH to the Compose bind-mounted data/app.db"
        )
    uri = DATABASE_PATH.resolve().as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=5)
    connection.row_factory = sqlite3.Row
    return connection


def rows(sql, parameters=()):
    connection = database()
    try:
        return connection.execute(sql, parameters).fetchall()
    finally:
        connection.close()


def row(sql, parameters=()):
    matches = rows(sql, parameters)
    return matches[0] if matches else None


def event_stream(text):
    events = []
    for block in text.replace("\r\n", "\n").strip().split("\n\n"):
        event_name = "message"
        data = []
        for line in block.split("\n"):
            if line.startswith("event:"):
                event_name = line[6:].strip()
            elif line.startswith("data:"):
                data.append(line[5:].strip())
        if data:
            events.append((event_name, json.loads("\n".join(data))))
    return events
