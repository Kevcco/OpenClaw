import os
from pathlib import Path

from flask import Flask, jsonify


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    project_root = Path(__file__).resolve().parent.parent
    app.config.from_mapping(
        DATABASE_PATH=os.getenv("DATABASE_PATH", str(project_root / "data" / "app.db")),
        UPLOAD_DIR=os.getenv("UPLOAD_DIR", str(project_root / "uploads")),
        MAX_CONTENT_LENGTH=5 * 1024 * 1024,
    )

    if test_config is not None:
        app.config.update(test_config)

    secret_key = app.config.get("SECRET_KEY") or os.getenv("SECRET_KEY")
    if not secret_key:
        raise RuntimeError("SECRET_KEY must be provided by the environment")
    app.config["SECRET_KEY"] = secret_key
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    from .auth import bp as auth_bp
    from .materials import bp as materials_bp
    from . import db

    app.register_blueprint(auth_bp)
    app.register_blueprint(materials_bp)
    db.init_app(app)

    @app.get("/health")
    def health():
        return jsonify(status="ok")

    @app.errorhandler(413)
    def request_too_large(_error):
        return {"error": "file too large"}, 400

    return app
