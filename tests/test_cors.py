from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_cors_allows_local_frontend():
    response = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert (
        response.headers.get("access-control-allow-origin") == "http://localhost:3000"
    )


def test_cors_blocks_unknown_origin():
    response = client.get("/health", headers={"Origin": "https://evil.example"})
    assert response.headers.get("access-control-allow-origin") is None
