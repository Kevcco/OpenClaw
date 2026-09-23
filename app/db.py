import sqlite3
from pathlib import Path

import bcrypt
from flask import current_app, g


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS classes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('teacher', 'student')),
    class_id INTEGER NOT NULL REFERENCES classes(id)
);

CREATE TABLE IF NOT EXISTS lectures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    class_id INTEGER REFERENCES classes(id),
    UNIQUE (class_id, title)
);

CREATE TABLE IF NOT EXISTS assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    class_id INTEGER REFERENCES classes(id),
    UNIQUE (class_id, title)
);

CREATE TABLE IF NOT EXISTS assistants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    class_id INTEGER REFERENCES classes(id),
    UNIQUE (class_id, name)
);

CREATE TABLE IF NOT EXISTS skills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    class_id INTEGER REFERENCES classes(id),
    UNIQUE (class_id, name)
);

CREATE TABLE IF NOT EXISTS materials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    class_id INTEGER NOT NULL REFERENCES classes(id),
    file_path TEXT NOT NULL,
    uploaded_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (class_id, title)
);

CREATE TABLE IF NOT EXISTS knowledge_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    material_id INTEGER NOT NULL UNIQUE REFERENCES materials(id) ON DELETE CASCADE,
    class_id INTEGER NOT NULL REFERENCES classes(id),
    body_text TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_users_class_id ON users(class_id);
CREATE INDEX IF NOT EXISTS idx_materials_class_id ON materials(class_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_entries_class_id ON knowledge_entries(class_id);
"""

SEED_CREDENTIALS = {
    "teacher_a": "teacher_a_pass",
    "student_a1": "student_a1_pass",
    "student_b1": "student_b1_pass",
}


def connect(database_path):
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def get_db():
    if "db" not in g:
        database_path = Path(current_app.config["DATABASE_PATH"])
        database_path.parent.mkdir(parents=True, exist_ok=True)
        g.db = connect(database_path)
    return g.db


def close_db(_error=None):
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


def init_app(app):
    app.teardown_appcontext(close_db)


def init_schema(connection):
    connection.executescript(SCHEMA_SQL)
    connection.commit()


def _class_ids(connection):
    return {
        row["name"]: row["id"]
        for row in connection.execute("SELECT id, name FROM classes").fetchall()
    }


def _user_ids(connection):
    return {
        row["username"]: row["id"]
        for row in connection.execute("SELECT id, username FROM users").fetchall()
    }


def seed_data(connection, upload_dir):
    upload_root = Path(upload_dir)
    upload_root.mkdir(parents=True, exist_ok=True)
    connection.executemany(
        "INSERT OR IGNORE INTO classes (name) VALUES (?)",
        [("A班",), ("B班",)],
    )
    class_ids = _class_ids(connection)
    users = [
        ("teacher_a", "teacher", class_ids["A班"]),
        ("student_a1", "student", class_ids["A班"]),
        ("student_b1", "student", class_ids["B班"]),
    ]
    for username, role, class_id in users:
        password_hash = bcrypt.hashpw(
            SEED_CREDENTIALS[username].encode("utf-8"), bcrypt.gensalt()
        ).decode("ascii")
        connection.execute(
            """
            INSERT OR IGNORE INTO users (username, password_hash, role, class_id)
            VALUES (?, ?, ?, ?)
            """,
            (username, password_hash, role, class_id),
        )
    user_ids = _user_ids(connection)
    connection.executemany(
        "INSERT OR IGNORE INTO lectures (title, class_id) VALUES (?, ?)",
        [("A班讲义占位", class_ids["A班"]), ("B班讲义占位", class_ids["B班"])],
    )
    connection.executemany(
        "INSERT OR IGNORE INTO assignments (title, class_id) VALUES (?, ?)",
        [("A班作业占位", class_ids["A班"]), ("B班作业占位", class_ids["B班"])],
    )
    connection.executemany(
        "INSERT OR IGNORE INTO assistants (name, class_id) VALUES (?, ?)",
        [("A班助手占位", class_ids["A班"]), ("B班助手占位", class_ids["B班"])],
    )
    connection.executemany(
        "INSERT OR IGNORE INTO skills (name, class_id) VALUES (?, ?)",
        [("A班技能占位", class_ids["A班"]), ("B班技能占位", class_ids["B班"])],
    )
    seed_materials = [
        ("A班材料：一次函数基础", class_ids["A班"], user_ids["teacher_a"], "A班材料正文：一次函数基础。", "seed-a.md"),
        ("B班材料：几何图形基础", class_ids["B班"], user_ids["teacher_a"], "B班材料正文：几何图形基础。", "seed-b.md"),
    ]
    for title, class_id, uploaded_by, body_text, filename in seed_materials:
        relative_path = Path(str(class_id)) / filename
        destination = upload_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(body_text, encoding="utf-8")
        connection.execute(
            """
            INSERT OR IGNORE INTO materials (title, class_id, file_path, uploaded_by)
            VALUES (?, ?, ?, ?)
            """,
            (title, class_id, str(relative_path), uploaded_by),
        )
        material = connection.execute(
            "SELECT id FROM materials WHERE class_id = ? AND title = ?",
            (class_id, title),
        ).fetchone()
        connection.execute(
            """
            INSERT OR IGNORE INTO knowledge_entries (material_id, class_id, body_text)
            VALUES (?, ?, ?)
            """,
            (material["id"], class_id, body_text),
        )
    connection.commit()


def list_materials(class_id, search=None):
    query = "SELECT id, title, class_id, file_path, uploaded_by, created_at FROM materials WHERE class_id = ?"
    params = [class_id]
    if search:
        query += " AND title LIKE ?"
        params.append(f"%{search}%")
    query += " ORDER BY id"
    return get_db().execute(query, params).fetchall()


def get_material(material_id, class_id=None):
    if class_id is None:
        return get_db().execute(
            "SELECT * FROM materials WHERE id = ?", (material_id,)
        ).fetchone()
    return get_db().execute(
        "SELECT * FROM materials WHERE id = ? AND class_id = ?",
        (material_id, class_id),
    ).fetchone()


def get_material_with_knowledge(material_id, class_id):
    return get_db().execute(
        """
        SELECT materials.*, knowledge_entries.body_text
        FROM materials
        JOIN knowledge_entries ON knowledge_entries.material_id = materials.id
        WHERE materials.id = ? AND materials.class_id = ?
        """,
        (material_id, class_id),
    ).fetchone()
