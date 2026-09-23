import pytest

from app import create_app


@pytest.fixture()
def app(tmp_path):
    database_path = tmp_path / "test.db"
    upload_dir = tmp_path / "uploads"
    return create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret-key",
            "DATABASE_PATH": str(database_path),
            "UPLOAD_DIR": str(upload_dir),
        }
    )


@pytest.fixture()
def client(app):
    return app.test_client()
