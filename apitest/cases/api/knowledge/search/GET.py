from urllib.parse import urlencode

from support import ACCOUNTS, login, request, row


def run():
    token_a, _ = login("student_a")
    token_b, _ = login("student_b")
    path = "/api/knowledge/search?" + urlencode({"q": "一次函数", "mode": "keyword", "limit": 10})
    result_a = request("GET", path, token=token_a)
    result_b = request("GET", path, token=token_b)
    assert result_a["status"] == result_b["status"] == 200
    assert result_a["json"]["hits"]

    user_a = row("SELECT class_id FROM users WHERE username = ?", (ACCOUNTS["student_a"][0],))
    class_b = row("SELECT class_id FROM users WHERE username = ?", (ACCOUNTS["student_b"][0],))

    for result, class_id in ((result_a, user_a["class_id"]), (result_b, class_b["class_id"])):
        for hit in result["json"]["hits"]:
            source = hit["source"]
            assert row(
                """SELECT id FROM knowledge_chunks
                   WHERE material_id = ? AND class_id = ? AND chunk_index = ?""",
                (source["material_id"], class_id, source["chunk_index"]),
            ) is not None
    return f"A/B search results map only to their authenticated class chunks (A={len(result_a['json']['hits'])}, B={len(result_b['json']['hits'])})"
