"""Grant or revoke audit administrator access using local database access only."""

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.db import connect, grant_admin, init_schema, revoke_admin


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("grant", "revoke"))
    parser.add_argument("username")
    parser.add_argument("--granted-by", default="local-cli")
    arguments = parser.parse_args()
    database_path = Path(os.getenv("DATABASE_PATH", str(PROJECT_ROOT / "data" / "app.db")))
    connection = connect(database_path)
    try:
        init_schema(connection)
        if arguments.action == "grant":
            changed = grant_admin(connection, arguments.username, arguments.granted_by)
            if not changed:
                parser.error("unknown username")
        else:
            changed = revoke_admin(connection, arguments.username)
        print(f"{'updated' if changed else 'unchanged'} {arguments.action} for {arguments.username}")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
