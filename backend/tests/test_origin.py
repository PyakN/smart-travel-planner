from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.origin import OriginGuard

SECRET = "a-long-random-value"


def guarded(secret: str | None) -> TestClient:
    app = FastAPI()
    app.add_middleware(OriginGuard, secret=lambda: secret)

    @app.get("/cities")
    def cities() -> list[str]:
        return ["lisbon"]

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return TestClient(app)


def test_without_a_secret_every_request_is_answered() -> None:
    assert guarded(None).get("/cities").status_code == 200
    assert guarded("").get("/cities").status_code == 200


def test_requests_without_the_secret_are_refused() -> None:
    client = guarded(SECRET)
    for headers in ({}, {"X-Origin-Secret": "a-guess"}, {"X-Origin-Secret": ""}):
        response = client.get("/cities", headers=headers)
        assert response.status_code == 403
        assert response.json() == {"detail": "Requests go through the website."}


def test_requests_with_the_secret_are_answered() -> None:
    response = guarded(SECRET).get("/cities", headers={"X-Origin-Secret": SECRET})
    assert response.status_code == 200
    assert response.json() == ["lisbon"]


def test_health_stays_open_for_the_hosts_checks() -> None:
    assert guarded(SECRET).get("/health").status_code == 200
