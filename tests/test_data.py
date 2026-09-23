from app import db


def test_seeded_material_queries_are_class_scoped(app):
    connection = db.connect(app.config["DATABASE_PATH"])
    db.init_schema(connection)
    db.seed_data(connection, app.config["UPLOAD_DIR"])
    connection.close()

    with app.app_context():
        rows = db.list_materials(1)
        assert rows
        assert all(row["class_id"] == 1 for row in rows)
        assert all("B班" not in row["title"] for row in rows)
