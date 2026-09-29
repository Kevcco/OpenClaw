import hashlib
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

CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    knowledge_entry_id INTEGER NOT NULL REFERENCES knowledge_entries(id) ON DELETE CASCADE,
    material_id INTEGER NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
    class_id INTEGER NOT NULL REFERENCES classes(id),
    chunk_index INTEGER NOT NULL,
    chunk_text TEXT NOT NULL,
    start_offset INTEGER NOT NULL,
    end_offset INTEGER NOT NULL,
    offset_basis TEXT NOT NULL DEFAULT 'body_text',
    strategy TEXT NOT NULL DEFAULT 'auto',
    strategy_version TEXT NOT NULL DEFAULT '1',
    content_hash TEXT NOT NULL,
    index_status TEXT NOT NULL DEFAULT 'pending' CHECK (index_status IN ('pending', 'ready', 'failed')),
    vector_status TEXT NOT NULL DEFAULT 'pending' CHECK (vector_status IN ('pending', 'ready', 'failed', 'unavailable')),
    index_error TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (material_id, chunk_index, strategy, strategy_version)
);

CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(
    chunk_id UNINDEXED,
    class_id UNINDEXED,
    chunk_text,
    tokenize = 'trigram'
);

CREATE INDEX IF NOT EXISTS idx_users_class_id ON users(class_id);
CREATE INDEX IF NOT EXISTS idx_materials_class_id ON materials(class_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_entries_class_id ON knowledge_entries(class_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_material_id ON knowledge_chunks(material_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_class_status ON knowledge_chunks(class_id, index_status);
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_entry_id ON knowledge_chunks(knowledge_entry_id);
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
    chunk_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(knowledge_chunks)")
    }
    if "vector_status" not in chunk_columns:
        connection.execute(
            "ALTER TABLE knowledge_chunks ADD COLUMN vector_status TEXT NOT NULL DEFAULT 'pending'"
        )
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


def list_knowledge_chunks(material_id, class_id=None, *, statuses=None, connection=None):
    query = "SELECT * FROM knowledge_chunks WHERE material_id = ?"
    params = [material_id]
    if class_id is not None:
        query += " AND class_id = ?"
        params.append(class_id)
    if statuses:
        placeholders = ",".join("?" for _ in statuses)
        query += f" AND index_status IN ({placeholders})"
        params.extend(statuses)
    query += " ORDER BY chunk_index, id"
    return (connection or get_db()).execute(query, params).fetchall()


def delete_knowledge_chunks(connection, material_id):
    rows = connection.execute(
        "SELECT id FROM knowledge_chunks WHERE material_id = ?", (material_id,)
    ).fetchall()
    for row in rows:
        connection.execute("DELETE FROM knowledge_fts WHERE chunk_id = ?", (str(row["id"]),))
    connection.execute("DELETE FROM knowledge_chunks WHERE material_id = ?", (material_id,))
    return [row["id"] for row in rows]


def insert_knowledge_chunk(connection, *, knowledge_entry_id, material_id, class_id, chunk):
    cursor = connection.execute(
        """
        INSERT INTO knowledge_chunks (
            knowledge_entry_id, material_id, class_id, chunk_index, chunk_text,
            start_offset, end_offset, offset_basis, strategy, strategy_version,
            content_hash, index_status, vector_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ready', 'pending')
        """,
        (
            knowledge_entry_id,
            material_id,
            class_id,
            chunk.index,
            chunk.text,
            chunk.start_offset,
            chunk.end_offset,
            chunk.offset_basis,
            chunk.strategy,
            chunk.strategy_version,
            hashlib.sha256(chunk.text.encode("utf-8")).hexdigest(),
        ),
    )
    chunk_id = cursor.lastrowid
    connection.execute(
        "INSERT INTO knowledge_fts (chunk_id, class_id, chunk_text) VALUES (?, ?, ?)",
        (str(chunk_id), str(class_id), chunk.text),
    )
    return chunk_id


def update_chunk_vector_status(connection, chunk_ids, status, error=None):
    if not chunk_ids:
        return
    placeholders = ",".join("?" for _ in chunk_ids)
    connection.execute(
        f"UPDATE knowledge_chunks SET vector_status = ?, index_error = ? WHERE id IN ({placeholders})",
        [status, error, *chunk_ids],
    )


def search_knowledge_keyword(connection, class_id, query, limit):
    safe_query = " ".join(query.replace('"', " ").split())
    if not safe_query:
        return []
    try:
        rows = connection.execute(
            """
            SELECT kc.*, m.title, m.created_at, fts.rank AS fts_rank
            FROM knowledge_fts AS fts
            JOIN knowledge_chunks AS kc ON CAST(fts.chunk_id AS INTEGER) = kc.id
            JOIN materials AS m ON m.id = kc.material_id AND m.class_id = kc.class_id
            WHERE fts MATCH ? AND kc.class_id = ? AND kc.index_status = 'ready'
            ORDER BY fts.rank ASC, kc.id ASC
            LIMIT ?
            """,
            (safe_query, class_id, limit),
        ).fetchall()
    except Exception:
        rows = []
    if rows:
        return rows
    return connection.execute(
        """
        SELECT kc.*, m.title, m.created_at, 0.0 AS fts_rank
        FROM knowledge_chunks AS kc
        JOIN materials AS m ON m.id = kc.material_id AND m.class_id = kc.class_id
        WHERE kc.class_id = ? AND kc.index_status = 'ready' AND kc.chunk_text LIKE ?
        ORDER BY kc.id ASC
        LIMIT ?
        """,
        (class_id, f"%{query}%", limit),
    ).fetchall()


def get_chunks_by_ids(connection, class_id, chunk_ids, *, ready_only=True):
    if not chunk_ids:
        return []
    placeholders = ",".join("?" for _ in chunk_ids)
    status_clause = " AND kc.index_status = 'ready'" if ready_only else ""
    rows = connection.execute(
        f"""
        SELECT kc.*, m.title, m.created_at
        FROM knowledge_chunks AS kc
        JOIN materials AS m ON m.id = kc.material_id AND m.class_id = kc.class_id
        WHERE kc.class_id = ? AND kc.id IN ({placeholders}){status_clause}
        """,
        [class_id, *chunk_ids],
    ).fetchall()
    by_id = {row["id"]: row for row in rows}
    return [by_id[chunk_id] for chunk_id in chunk_ids if chunk_id in by_id]
