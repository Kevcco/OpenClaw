"""Rebuild persisted knowledge chunks and vector points."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from app import db, indexing
from app.vector_store import build_embedding_provider, build_vector_store


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--material-id", type=int)
    parser.add_argument("--class-id", type=int)
    parser.add_argument("--strategy", choices=("auto", "custom", "hierarchy"), default="auto")
    parser.add_argument("--max-chars", type=int, default=800)
    parser.add_argument("--overlap-chars", type=int, default=80)
    parser.add_argument("--remove-urls", action="store_true")
    parser.add_argument("--collapse-whitespace", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    project_root = Path(__file__).resolve().parent.parent
    database_path = Path(os.getenv("DATABASE_PATH", project_root / "data" / "app.db"))
    connection = db.connect(database_path)
    config = {
        "QDRANT_URL": os.getenv("QDRANT_URL"),
        "QDRANT_COLLECTION": os.getenv("QDRANT_COLLECTION", "campusclaw_chunks"),
        "QDRANT_TIMEOUT": os.getenv("QDRANT_TIMEOUT", "10"),
        "EMBEDDING_MODE": os.getenv("EMBEDDING_MODE", "hash"),
        "EMBEDDING_API_URL": os.getenv("EMBEDDING_API_URL"),
        "EMBEDDING_API_KEY": os.getenv("EMBEDDING_API_KEY"),
    }
    provider = build_embedding_provider(config)
    vector_store = build_vector_store(config)
    query = "SELECT id FROM materials"
    params = []
    if args.material_id is not None:
        query += " WHERE id = ?"
        params.append(args.material_id)
    elif args.class_id is not None:
        query += " WHERE class_id = ?"
        params.append(args.class_id)
    query += " ORDER BY id"
    material_ids = [row["id"] for row in connection.execute(query, params).fetchall()]
    results = []
    try:
        for material_id in material_ids:
            results.append(
                indexing.rebuild_material(
                    connection,
                    material_id,
                    strategy=args.strategy,
                    max_chars=args.max_chars,
                    overlap_chars=args.overlap_chars,
                    remove_urls=args.remove_urls,
                    collapse_whitespace=args.collapse_whitespace,
                    embedding_provider=provider,
                    vector_store=vector_store,
                )
            )
    finally:
        connection.close()
    print(json.dumps({"materials": results}, ensure_ascii=False))


if __name__ == "__main__":
    main()
