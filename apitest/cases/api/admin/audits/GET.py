from support import login, request


def run():
    teacher, _ = login("teacher_a")
    student, _ = login("student_a")
    teacher_result = request("GET", "/api/admin/audits?limit=1", token=teacher)
    student_result = request("GET", "/api/admin/audits?limit=1", token=student)
    assert teacher_result["status"] == student_result["status"] == 403
    assert teacher_result["json"] == student_result["json"] == {"error": "forbidden"}
    return "Unprivileged teacher and student both receive opaque 403 from the audit API"
