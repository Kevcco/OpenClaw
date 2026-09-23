import os
import uuid
from pathlib import Path

from flask import (
    Blueprint,
    abort,
    current_app,
    jsonify,
    render_template,
    request,
    send_file,
)

from . import db
from .auth import current_user, login_required, role_required
from . import knowledge


bp = Blueprint("materials", __name__)


def material_json(row):
    return {
        "id": row["id"],
        "title": row["title"],
        "class_id": row["class_id"],
        "created_at": row["created_at"],
    }


@bp.route("/materials")
@login_required
def materials_page():
    user = current_user()
    rows = db.list_materials(user["class_id"], request.args.get("q"))
    return render_template("materials.html", materials=rows, user=user)


@bp.route("/api/materials")
@login_required
def materials_api():
    user = current_user()
    rows = db.list_materials(user["class_id"], request.args.get("q"))
    return jsonify({"materials": [material_json(row) for row in rows]})


@bp.route("/api/materials/<int:material_id>", methods=("GET", "PATCH", "DELETE"))
@login_required
def material_detail(material_id):
    user = current_user()
    row = db.get_material_with_knowledge(material_id, user["class_id"])
    if row is None:
        abort(404)

    if request.method == "GET":
        return jsonify({**material_json(row), "body_text": row["body_text"]})

    if user["role"] != "teacher":
        return jsonify({"error": "forbidden"}), 403

    if request.method == "PATCH":
        payload = request.get_json(silent=True) or {}
        title = (payload.get("title") or "").strip()
        if not title:
            return jsonify({"error": "title is required"}), 400
        try:
            db.get_db().execute(
                "UPDATE materials SET title = ? WHERE id = ? AND class_id = ?",
                (title, material_id, user["class_id"]),
            )
            db.get_db().commit()
        except Exception:
            db.get_db().rollback()
            return jsonify({"error": "title already exists"}), 409
        return jsonify({"id": material_id, "title": title})

    connection = db.get_db()
    connection.execute(
        "DELETE FROM materials WHERE id = ? AND class_id = ?",
        (material_id, user["class_id"]),
    )
    connection.commit()
    file_path = Path(current_app_upload_dir()) / row["file_path"]
    if file_path.is_file():
        file_path.unlink()
    return jsonify({"status": "deleted"})


def current_app_upload_dir():
    from flask import current_app

    return current_app.config["UPLOAD_DIR"]


@bp.route("/api/materials/<int:material_id>/download")
@login_required
def material_download(material_id):
    user = current_user()
    row = db.get_material(material_id, user["class_id"])
    if row is None:
        abort(404)
    file_path = Path(current_app_upload_dir()) / row["file_path"]
    if not file_path.is_file():
        abort(404)
    return send_file(file_path, as_attachment=True, download_name=Path(row["file_path"]).name)


@bp.route("/api/materials/upload", methods=("POST",))
@bp.route("/materials/upload", methods=("POST",))
@role_required("teacher")
def material_upload():
    user = current_user()
    uploaded_file = request.files.get("file")
    if uploaded_file is None:
        return jsonify({"error": "file is required"}), 400
    title = (request.form.get("title") or Path(uploaded_file.filename or "").stem).strip()
    if not title:
        return jsonify({"error": "title is required"}), 400

    max_bytes = int(current_app.config.get("MAX_UPLOAD_BYTES", 5 * 1024 * 1024))
    try:
        filename, body_text = knowledge.parse_upload(uploaded_file, max_bytes)
    except knowledge.UploadError as error:
        return jsonify({"error": str(error)}), 400

    relative_path = Path(str(user["class_id"])) / f"{uuid.uuid4().hex}_{filename}"
    relative_name = relative_path.as_posix()
    upload_root = Path(current_app.config["UPLOAD_DIR"])
    temporary_path = upload_root / f".{uuid.uuid4().hex}.part"
    final_path = upload_root / relative_path
    temporary_path.parent.mkdir(parents=True, exist_ok=True)
    final_path.parent.mkdir(parents=True, exist_ok=True)
    connection = db.get_db()
    material_id = None
    try:
        temporary_path.write_text(body_text, encoding="utf-8")
        material_id = knowledge.persist_material(
            connection,
            title=title,
            class_id=user["class_id"],
            file_path=relative_name,
            uploaded_by=user["id"],
            body_text=body_text,
        )
        os.replace(temporary_path, final_path)
        connection.commit()
    except Exception:
        connection.rollback()
        if temporary_path.exists():
            temporary_path.unlink()
        if final_path.exists():
            final_path.unlink()
        return jsonify({"error": "upload failed"}), 500

    return jsonify({"material_id": material_id, "title": title}), 201
