import os
from pathlib import Path

from flask import Flask, jsonify


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    project_root = Path(__file__).resolve().parent.parent
    app.config.from_mapping(
        DATABASE_PATH=os.getenv("DATABASE_PATH", str(project_root / "data" / "app.db")),
        UPLOAD_DIR=os.getenv("UPLOAD_DIR", str(project_root / "uploads")),
        TOKEN_HASH_SECRET=os.getenv("TOKEN_HASH_SECRET"),
        ACCESS_TOKEN_TTL_SECONDS=os.getenv("ACCESS_TOKEN_TTL_SECONDS", "28800"),
        MAX_CONTENT_LENGTH=5 * 1024 * 1024,
        QDRANT_URL=os.getenv("QDRANT_URL"),
        QDRANT_COLLECTION=os.getenv("QDRANT_COLLECTION", "campusclaw_chunks"),
        QDRANT_TIMEOUT=float(os.getenv("QDRANT_TIMEOUT", "10")),
        EMBEDDING_MODE=os.getenv("EMBEDDING_MODE", "hash"),
        EMBEDDING_API_URL=os.getenv("EMBEDDING_API_URL"),
        EMBEDDING_API_KEY=os.getenv("EMBEDDING_API_KEY"),
        EMBEDDING_TIMEOUT=float(os.getenv("EMBEDDING_TIMEOUT", "10")),
        VECTOR_STORE_MODE=os.getenv("VECTOR_STORE_MODE"),
        ANSWER_MODE=os.getenv("ANSWER_MODE", "extractive"),
        ANSWER_API_URL=os.getenv("ANSWER_API_URL"),
        ANSWER_API_BASE_URL=os.getenv("ANSWER_API_BASE_URL"),
        ANSWER_MODEL=os.getenv("ANSWER_MODEL"),
        ANSWER_API_KEY=os.getenv("ANSWER_API_KEY"),
        ANSWER_TIMEOUT=float(os.getenv("ANSWER_TIMEOUT", "20")),
    )

    if test_config is not None:
        app.config.update(test_config)

    token_hash_secret = app.config.get("TOKEN_HASH_SECRET")
    if not token_hash_secret:
        raise RuntimeError("TOKEN_HASH_SECRET must be provided by the environment")
    app.config["TOKEN_HASH_SECRET"] = token_hash_secret
    try:
        token_ttl = int(app.config.get("ACCESS_TOKEN_TTL_SECONDS", 28800))
    except (TypeError, ValueError) as error:
        raise RuntimeError("ACCESS_TOKEN_TTL_SECONDS must be a positive integer") from error
    if token_ttl <= 0:
        raise RuntimeError("ACCESS_TOKEN_TTL_SECONDS must be a positive integer")
    app.config["ACCESS_TOKEN_TTL_SECONDS"] = token_ttl

    from .auth import bp as auth_bp
    from .materials import bp as materials_bp
    from .retrieval_routes import bp as retrieval_bp
    from . import db, indexing
    from .answer import build_answer_provider
    from .vector_store import build_embedding_provider, build_vector_store

    app.register_blueprint(auth_bp)
    app.register_blueprint(materials_bp)
    app.register_blueprint(retrieval_bp)
    db.init_app(app)
    app.extensions["knowledge_embedding_provider"] = build_embedding_provider(app.config)
    app.extensions["knowledge_vector_store"] = build_vector_store(app.config)
    app.extensions["answer_provider"] = build_answer_provider(app.config)
    app.extensions["knowledge_reconciled"] = False

    @app.before_request
    def reconcile_knowledge_once():
        if app.extensions["knowledge_reconciled"]:
            return
        try:
            connection = db.get_db()
            connection.execute("SELECT 1 FROM knowledge_chunks LIMIT 1").fetchone()
            indexing.reconcile(
                connection,
                embedding_provider=app.extensions["knowledge_embedding_provider"],
                vector_store=app.extensions["knowledge_vector_store"],
            )
        except Exception:
            # Database initialization and external services may be staged separately.
            # The explicit rebuild command remains the recovery path.
            return
        app.extensions["knowledge_reconciled"] = True

    @app.get("/health")
    def health():
        return jsonify(status="ok")

    @app.errorhandler(413)
    def request_too_large(_error):
        return {"error": "file too large"}, 400

    return app
