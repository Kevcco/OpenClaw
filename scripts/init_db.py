import os
from pathlib import Path

from app.db import connect, init_schema, seed_data


def main():
    project_root = Path(__file__).resolve().parent.parent
    database_path = Path(
        os.getenv("DATABASE_PATH", str(project_root / "data" / "app.db"))
    )
    upload_dir = Path(
        os.getenv("UPLOAD_DIR", str(project_root / "uploads"))
    )
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = connect(database_path)
    try:
        init_schema(connection)
        seed_data(connection, upload_dir)
    finally:
        connection.close()
    print(f"initialized {database_path}")


if __name__ == "__main__":
    main()
