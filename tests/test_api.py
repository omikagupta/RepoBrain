from pathlib import Path
from typing import NoReturn

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from repobrain.main import create_app
from repobrain.settings import Settings


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Settings:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("REPOBRAIN_LOG_LEVEL", "INFO")
    return Settings()


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))


def test_health_returns_stable_status(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}
    assert len(response.headers["x-request-id"]) == 32


def test_unknown_route_preserves_request_id(client: TestClient) -> None:
    response = client.get("/missing", headers={"X-Request-ID": "test-request"})
    assert response.status_code == 404
    assert response.headers["x-request-id"] == "test-request"
    assert response.json() == {
        "error": {
            "code": "http_404",
            "message": "Not Found",
            "request_id": "test-request",
        }
    }


def test_wrong_method_preserves_allow_header(client: TestClient) -> None:
    response = client.post("/healthz", headers={"X-Request-ID": "invalid request id"})
    assert response.status_code == 405
    assert response.headers["allow"] == "GET"
    assert response.headers["x-request-id"] != "invalid request id"
    assert response.json()["error"]["request_id"] == response.headers["x-request-id"]


def test_validation_and_unexpected_errors(settings: Settings) -> None:
    app = create_app(settings)

    @app.get("/items/{item_id}", response_model=None)
    async def fail(item_id: int) -> NoReturn:
        raise RuntimeError("private exception details")

    with TestClient(app) as client:
        invalid = client.get("/items/invalid")
        failed = client.get("/items/1")

    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "validation_error"
    assert failed.status_code == 500
    assert failed.json() == {
        "error": {
            "code": "internal_error",
            "message": "Internal server error",
            "request_id": failed.headers["x-request-id"],
        }
    }


def test_invalid_log_level_prevents_startup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("REPOBRAIN_LOG_LEVEL", "invalid")
    with pytest.raises(ValidationError, match="log_level"):
        create_app()
