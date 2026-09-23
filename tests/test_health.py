def test_health_is_public_and_returns_json(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.is_json
    assert response.get_json() == {"status": "ok"}
    assert response.location is None

