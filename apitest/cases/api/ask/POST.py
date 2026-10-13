from support import login, request, row


def run():
    token, _ = login("student_a")
    result = request("POST", "/api/ask", token=token, payload={"question": "一次函数"})
    assert result["status"] == 200 and result["json"].get("audit_id")
    assert isinstance(result["json"].get("citations"), list)
    audit = row(
        "SELECT operation, status FROM assistant_audit_operations WHERE audit_id = ?",
        (result["json"]["audit_id"],),
    )
    assert audit is not None and audit["operation"] == "ask"
    assert audit["status"] in {"complete", "no-evidence"}
    return f"Single-turn answer audit {result['json']['audit_id']} is queryable and content-minimized"
