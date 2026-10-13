import hashlib
import json
import secrets
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

CREATE TABLE IF NOT EXISTS auth_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_hash TEXT NOT NULL UNIQUE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    issued_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    revoked_at INTEGER
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

CREATE TABLE IF NOT EXISTS assistant_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id INTEGER NOT NULL UNIQUE REFERENCES classes(id) ON DELETE CASCADE,
    prompt TEXT NOT NULL,
    prompt_version INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS assistant_skills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
    skill_key TEXT NOT NULL,
    name TEXT NOT NULL,
    instruction TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    version INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (class_id, skill_key)
);

CREATE TABLE IF NOT EXISTS assistant_skill_settings_versions (
    class_id INTEGER PRIMARY KEY REFERENCES classes(id) ON DELETE CASCADE,
    version INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS admin_principals (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    granted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    granted_by TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assistant_audit_operations (
    audit_id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    class_id INTEGER NOT NULL,
    operation TEXT NOT NULL CHECK (operation IN ('search', 'ask', 'conversation')),
    status TEXT NOT NULL CHECK (status IN ('processing', 'complete', 'no-evidence', 'failed', 'interrupted')),
    skill_decisions_json TEXT NOT NULL DEFAULT '[]',
    conversation_message_id INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS assistant_audit_hits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    audit_id TEXT NOT NULL REFERENCES assistant_audit_operations(audit_id) ON DELETE CASCADE,
    material_id INTEGER NOT NULL,
    chunk_id INTEGER NOT NULL,
    source_title TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    rank INTEGER NOT NULL,
    score REAL,
    matched_modes_json TEXT NOT NULL DEFAULT '[]',
    citation_index INTEGER
);

CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS conversation_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    owner_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'complete' CHECK (status IN ('pending', 'streaming', 'complete', 'failed')),
    citations_json TEXT NOT NULL DEFAULT '[]',
    prompt_version INTEGER,
    skill_version INTEGER,
    skill_snapshot_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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
CREATE INDEX IF NOT EXISTS idx_auth_tokens_hash ON auth_tokens(token_hash);
CREATE INDEX IF NOT EXISTS idx_auth_tokens_user_id ON auth_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_auth_tokens_expiry ON auth_tokens(expires_at, revoked_at);
CREATE INDEX IF NOT EXISTS idx_materials_class_id ON materials(class_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_entries_class_id ON knowledge_entries(class_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_material_id ON knowledge_chunks(material_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_class_status ON knowledge_chunks(class_id, index_status);
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_entry_id ON knowledge_chunks(knowledge_entry_id);
CREATE INDEX IF NOT EXISTS idx_assistant_skills_class ON assistant_skills(class_id, skill_key);
CREATE INDEX IF NOT EXISTS idx_conversations_owner_class ON conversations(owner_user_id, class_id, updated_at);
CREATE INDEX IF NOT EXISTS idx_conversation_messages_conversation ON conversation_messages(conversation_id, owner_user_id, class_id, id);
CREATE INDEX IF NOT EXISTS idx_assistant_audit_class_time ON assistant_audit_operations(class_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_assistant_audit_user_time ON assistant_audit_operations(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_assistant_audit_operation_status ON assistant_audit_operations(operation, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_assistant_audit_hit_source ON assistant_audit_hits(material_id, chunk_id);
CREATE INDEX IF NOT EXISTS idx_assistant_audit_hit_operation ON assistant_audit_hits(audit_id, rank);
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
    message_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(conversation_messages)")
    }
    if "skill_snapshot_json" not in message_columns:
        connection.execute(
            "ALTER TABLE conversation_messages ADD COLUMN skill_snapshot_json TEXT NOT NULL DEFAULT '[]'"
        )
    connection.execute(
        """
        INSERT OR IGNORE INTO assistant_skill_settings_versions (class_id, version)
        SELECT class_id, 1 FROM assistant_skills GROUP BY class_id
        """
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


def seed_data(connection, upload_dir, skills_dir=None):
    from .skill_registry import load_registry

    upload_root = Path(upload_dir)
    upload_root.mkdir(parents=True, exist_ok=True)
    connection.executemany(
        "INSERT OR IGNORE INTO classes (name) VALUES (?)",
        [("A班",), ("B班",)],
    )
    class_ids = _class_ids(connection)
    assistant_prompt = (
        "你是 CampusClaw 的学习助手。请用清晰、耐心的中文回应学生，优先帮助学生理解问题。"
        "事实性回答必须以本轮检索到的本班材料为依据；依据不足时要明确说明。"
    )
    registry = load_registry(skills_dir or Path(__file__).resolve().parent.parent / "skills")
    for class_id in class_ids.values():
        connection.execute(
            "INSERT OR IGNORE INTO assistant_configs (class_id, prompt) VALUES (?, ?)",
            (class_id, assistant_prompt),
        )
        for key, package in registry.items():
            connection.execute(
                """
                INSERT OR IGNORE INTO assistant_skills
                    (class_id, skill_key, name, instruction, enabled)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    class_id,
                    key,
                    package["name"],
                    package["instruction"],
                    int(key == "solution-guidance"),
                ),
            )
        connection.execute(
            "INSERT OR IGNORE INTO assistant_skill_settings_versions (class_id, version) VALUES (?, 1)",
            (class_id,),
        )
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


def get_assistant_config(connection, class_id):
    return connection.execute(
        "SELECT * FROM assistant_configs WHERE class_id = ?", (class_id,)
    ).fetchone()


def update_assistant_prompt(connection, class_id, prompt):
    connection.execute(
        """
        UPDATE assistant_configs
        SET prompt = ?, prompt_version = prompt_version + 1, updated_at = CURRENT_TIMESTAMP
        WHERE class_id = ?
        """,
        (prompt, class_id),
    )
    connection.commit()
    return get_assistant_config(connection, class_id)


def get_assistant_skill(connection, class_id, skill_key="solution-guidance"):
    return connection.execute(
        "SELECT * FROM assistant_skills WHERE class_id = ? AND skill_key = ?",
        (class_id, skill_key),
    ).fetchone()


def update_assistant_skill(connection, class_id, enabled, skill_key="solution-guidance"):
    cursor = connection.execute(
        """
        UPDATE assistant_skills
        SET enabled = ?, version = version + 1, updated_at = CURRENT_TIMESTAMP
        WHERE class_id = ? AND skill_key = ?
        """,
        (int(bool(enabled)), class_id, skill_key),
    )
    if cursor.rowcount:
        connection.execute(
            """
            INSERT INTO assistant_skill_settings_versions (class_id, version)
            VALUES (?, 2)
            ON CONFLICT(class_id) DO UPDATE SET
                version = assistant_skill_settings_versions.version + 1,
                updated_at = CURRENT_TIMESTAMP
            """,
            (class_id,),
        )
    connection.commit()
    return get_assistant_skill(connection, class_id, skill_key)


def get_assistant_skill_settings_version(connection, class_id):
    row = connection.execute(
        "SELECT version FROM assistant_skill_settings_versions WHERE class_id = ?",
        (class_id,),
    ).fetchone()
    return row["version"] if row else 0


def list_assistant_skills(connection, class_id):
    return connection.execute(
        "SELECT * FROM assistant_skills WHERE class_id = ? ORDER BY skill_key",
        (class_id,),
    ).fetchall()


def is_admin(connection, user_id):
    return connection.execute(
        "SELECT 1 FROM admin_principals WHERE user_id = ?", (user_id,)
    ).fetchone() is not None


def grant_admin(connection, username, granted_by):
    user = connection.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if user is None:
        return False
    connection.execute(
        """
        INSERT INTO admin_principals (user_id, granted_by)
        VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET granted_by = ?, granted_at = CURRENT_TIMESTAMP
        """,
        (user["id"], granted_by, granted_by),
    )
    connection.commit()
    return True


def revoke_admin(connection, username):
    cursor = connection.execute(
        "DELETE FROM admin_principals WHERE user_id = (SELECT id FROM users WHERE username = ?)",
        (username,),
    )
    connection.commit()
    return cursor.rowcount > 0


def create_audit_operation(
    connection, *, user_id, class_id, operation, skill_decisions=None,
    conversation_message_id=None,
):
    audit_id = secrets.token_urlsafe(18)
    connection.execute(
        """
        INSERT INTO assistant_audit_operations
            (audit_id, user_id, class_id, operation, status,
             skill_decisions_json, conversation_message_id)
        VALUES (?, ?, ?, ?, 'processing', ?, ?)
        """,
        (
            audit_id,
            user_id,
            class_id,
            operation,
            json.dumps(skill_decisions or [], ensure_ascii=False, separators=(",", ":")),
            conversation_message_id,
        ),
    )
    connection.commit()
    return audit_id


def record_audit_hits(connection, audit_id, hits, citation_indexes=None):
    citation_indexes = citation_indexes or {}
    connection.execute("DELETE FROM assistant_audit_hits WHERE audit_id = ?", (audit_id,))
    for rank, (row, score, modes) in enumerate(hits, start=1):
        connection.execute(
            """
            INSERT INTO assistant_audit_hits
                (audit_id, material_id, chunk_id, source_title, chunk_index,
                 rank, score, matched_modes_json, citation_index)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                audit_id,
                row["material_id"],
                row["id"],
                row["title"],
                row["chunk_index"],
                rank,
                score,
                json.dumps(sorted(modes or []), ensure_ascii=False),
                citation_indexes.get(row["id"]),
            ),
        )
    connection.commit()


def finish_audit_operation(connection, audit_id, status):
    if status not in {"complete", "no-evidence", "failed", "interrupted"}:
        raise ValueError("invalid audit status")
    connection.execute(
        """
        UPDATE assistant_audit_operations
        SET status = ?, completed_at = CURRENT_TIMESTAMP
        WHERE audit_id = ?
        """,
        (status, audit_id),
    )
    connection.commit()


def list_audit_operations(connection, filters, *, limit, offset):
    clauses = []
    params = []
    columns = {
        "audit_id": "o.audit_id = ?",
        "class_id": "o.class_id = ?",
        "user_id": "o.user_id = ?",
        "operation": "o.operation = ?",
        "status": "o.status = ?",
        "created_after": "o.created_at >= ?",
        "created_before": "o.created_at <= ?",
    }
    for key, clause in columns.items():
        value = filters.get(key)
        if value is not None and value != "":
            clauses.append(clause)
            params.append(value)
    for key, expression in (("skill_key", "json_each.value"),):
        value = filters.get(key)
        if value:
            clauses.append(
                "EXISTS (SELECT 1 FROM json_each(o.skill_decisions_json) WHERE json_extract(json_each.value, '$.skill_key') = ?)"
            )
            params.append(value)
    for key, column in (("material_id", "h.material_id"), ("chunk_id", "h.chunk_id")):
        value = filters.get(key)
        if value is not None and value != "":
            clauses.append(
                f"EXISTS (SELECT 1 FROM assistant_audit_hits h WHERE h.audit_id = o.audit_id AND {column} = ?)"
            )
            params.append(value)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    rows = connection.execute(
        f"SELECT o.* FROM assistant_audit_operations o{where} ORDER BY o.created_at DESC, o.audit_id DESC LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()
    result = []
    for row in rows:
        hits = connection.execute(
            """
            SELECT material_id, chunk_id, source_title, chunk_index, rank,
                   score, matched_modes_json, citation_index
            FROM assistant_audit_hits WHERE audit_id = ? ORDER BY rank
            """,
            (row["audit_id"],),
        ).fetchall()
        try:
            decisions = json.loads(row["skill_decisions_json"] or "[]")
        except json.JSONDecodeError:
            decisions = []
        result.append(
            {
                "audit_id": row["audit_id"],
                "user_id": row["user_id"],
                "class_id": row["class_id"],
                "operation": row["operation"],
                "status": row["status"],
                "skill_decisions": decisions,
                "conversation_message_id": row["conversation_message_id"],
                "created_at": row["created_at"],
                "completed_at": row["completed_at"],
                "hits": [
                    {
                        "material_id": hit["material_id"],
                        "chunk_id": hit["chunk_id"],
                        "title": hit["source_title"],
                        "chunk_index": hit["chunk_index"],
                        "rank": hit["rank"],
                        "score": hit["score"],
                        "matched_modes": json.loads(hit["matched_modes_json"] or "[]"),
                        "citation_index": hit["citation_index"],
                    }
                    for hit in hits
                ],
            }
        )
    return result


def create_conversation(connection, owner_user_id, class_id, title):
    cursor = connection.execute(
        "INSERT INTO conversations (owner_user_id, class_id, title) VALUES (?, ?, ?)",
        (owner_user_id, class_id, title),
    )
    connection.commit()
    return get_conversation(connection, cursor.lastrowid, owner_user_id, class_id)


def list_conversations(connection, owner_user_id, class_id, limit=50):
    return connection.execute(
        """
        SELECT * FROM conversations
        WHERE owner_user_id = ? AND class_id = ?
        ORDER BY updated_at DESC, id DESC LIMIT ?
        """,
        (owner_user_id, class_id, limit),
    ).fetchall()


def get_conversation(connection, conversation_id, owner_user_id, class_id):
    return connection.execute(
        """
        SELECT * FROM conversations
        WHERE id = ? AND owner_user_id = ? AND class_id = ?
        """,
        (conversation_id, owner_user_id, class_id),
    ).fetchone()


def list_conversation_messages(connection, conversation_id, owner_user_id, class_id):
    return connection.execute(
        """
        SELECT * FROM conversation_messages
        WHERE conversation_id = ? AND owner_user_id = ? AND class_id = ?
        ORDER BY id
        """,
        (conversation_id, owner_user_id, class_id),
    ).fetchall()


def create_conversation_turn(
    connection, *, conversation_id, owner_user_id, class_id, question,
    prompt_version, skill_version, skill_snapshot=None,
):
    user_cursor = connection.execute(
        """
        INSERT INTO conversation_messages
            (conversation_id, owner_user_id, class_id, role, content, status)
        VALUES (?, ?, ?, 'user', ?, 'complete')
        """,
        (conversation_id, owner_user_id, class_id, question),
    )
    assistant_cursor = connection.execute(
        """
        INSERT INTO conversation_messages
            (conversation_id, owner_user_id, class_id, role, content, status,
             prompt_version, skill_version, skill_snapshot_json)
        VALUES (?, ?, ?, 'assistant', '', 'pending', ?, ?, ?)
        """,
        (
            conversation_id,
            owner_user_id,
            class_id,
            prompt_version,
            skill_version,
            json.dumps(skill_snapshot or [], ensure_ascii=False, separators=(",", ":")),
        ),
    )
    connection.execute(
        "UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = ? AND owner_user_id = ? AND class_id = ?",
        (conversation_id, owner_user_id, class_id),
    )
    connection.commit()
    return user_cursor.lastrowid, assistant_cursor.lastrowid


def update_conversation_message(connection, message_id, owner_user_id, class_id, *, content, status, citations=None):
    connection.execute(
        """
        UPDATE conversation_messages
        SET content = ?, status = ?, citations_json = ?
        WHERE id = ? AND owner_user_id = ? AND class_id = ? AND role = 'assistant'
        """,
        (
            content,
            status,
            json.dumps(citations or [], ensure_ascii=False),
            message_id,
            owner_user_id,
            class_id,
        ),
    )
    connection.commit()


def delete_conversation(connection, conversation_id, owner_user_id, class_id):
    cursor = connection.execute(
        "DELETE FROM conversations WHERE id = ? AND owner_user_id = ? AND class_id = ?",
        (conversation_id, owner_user_id, class_id),
    )
    connection.commit()
    return cursor.rowcount > 0


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
