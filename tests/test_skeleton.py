def test_test_client_isolated(client, app):
    assert client.get("/").status_code in {404, 302}
    assert not (app.config["DATABASE_PATH"] == "data/app.db")
    assert not (app.config["UPLOAD_DIR"] == "uploads")
