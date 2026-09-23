from pathlib import Path

from werkzeug.utils import secure_filename


ALLOWED_EXTENSIONS = {".txt", ".md"}


class UploadError(ValueError):
    pass


def parse_upload(file_storage, max_bytes):
    filename = secure_filename(file_storage.filename or "")
    if not filename:
        raise UploadError("filename is required")
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise UploadError("unsupported file type")
    content = file_storage.read(max_bytes + 1)
    if not content:
        raise UploadError("file is empty")
    if len(content) > max_bytes:
        raise UploadError("file is too large")
    try:
        body_text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise UploadError("file must be valid UTF-8") from error
    if not body_text.strip():
        raise UploadError("file is empty")
    return filename, body_text


def persist_material(connection, *, title, class_id, file_path, uploaded_by, body_text):
    cursor = connection.execute(
        """
        INSERT INTO materials (title, class_id, file_path, uploaded_by)
        VALUES (?, ?, ?, ?)
        """,
        (title, class_id, file_path, uploaded_by),
    )
    material_id = cursor.lastrowid
    connection.execute(
        """
        INSERT INTO knowledge_entries (material_id, class_id, body_text)
        VALUES (?, ?, ?)
        """,
        (material_id, class_id, body_text),
    )
    return material_id
