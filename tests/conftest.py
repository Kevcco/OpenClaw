import pytest

from app import create_app


@pytest.fixture()
def app(tmp_path):
    database_path = tmp_path / "test.db"
    upload_dir = tmp_path / "uploads"
    return create_app(
        {
            "TESTING": True,
            "TOKEN_HASH_SECRET": "test-token-hash-secret",
            "ACCESS_TOKEN_TTL_SECONDS": 28800,
            "DATABASE_PATH": str(database_path),
            "UPLOAD_DIR": str(upload_dir),
        }
    )


@pytest.fixture()
def client(app):
    return app.test_client()
