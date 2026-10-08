"""Autenticazione: login, protezione delle API, CSRF, limitazione tentativi, cambio password."""
import json

import pytest
from fastapi.testclient import TestClient

from app import auth as auth_mod
from app.auth import COOKIE_NAME, AuthService, hash_password, verify_password


@pytest.fixture
def client(tmp_path, monkeypatch):
    from app.api import server

    monkeypatch.setattr(server, "auth", AuthService(tmp_path))
    monkeypatch.setattr(auth_mod.time, "sleep", lambda s: None)  # niente attese nei test
    with TestClient(server.app) as c:
        yield c, tmp_path


def login(c, user="admin", pw="123"):
    return c.post("/api/auth/login", json={"username": user, "password": pw})


def test_password_hash_roundtrip():
    h = hash_password("segreta-123")
    assert h.startswith("scrypt$") and "segreta" not in h
    assert verify_password("segreta-123", h) and not verify_password("altra", h)


def test_api_requires_login(client):
    c, _ = client
    assert c.get("/api/runs").status_code == 401
    assert c.get("/api/settings").status_code == 401
    assert c.get("/api/auth/me").status_code == 401


def test_login_sets_secure_cookie_and_unlocks_api(client):
    c, data = client
    r = login(c)
    assert r.status_code == 200 and r.json() == {"user": "admin", "initial_password": True}
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert c.get("/api/runs").status_code == 200
    assert c.get("/api/auth/me").json()["user"] == "admin"
    stored = json.loads((data / "users.json").read_text())
    assert "123" not in stored["admin"]["hash"]


def test_wrong_credentials_are_generic(client):
    c, _ = client
    a = login(c, pw="sbagliata")
    b = login(c, user="nessuno", pw="x")
    assert a.status_code == b.status_code == 401
    assert a.json()["detail"] == b.json()["detail"]


def test_lockout_after_repeated_failures(client):
    c, _ = client
    for _ in range(5):
        assert login(c, pw="no").status_code == 401
    r = login(c)  # anche con la password giusta: bloccato
    assert r.status_code == 429 and int(r.headers["retry-after"]) > 0


def test_tampered_cookie_rejected(client):
    c, _ = client
    login(c)
    token = c.cookies.get(COOKIE_NAME)
    body, sig = token.rsplit(".", 1)
    c.cookies.set(COOKIE_NAME, body + "." + sig[::-1])
    assert c.get("/api/runs").status_code == 401


def test_cross_origin_writes_blocked(client):
    c, _ = client
    login(c)
    r = c.put("/api/settings", json={"run_budget_usd": 1}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    ok = c.put("/api/settings", json={"run_budget_usd": 0}, headers={"Origin": "http://testserver"})
    assert ok.status_code == 200


def test_change_password_invalidates_old_sessions(client):
    c, _ = client
    login(c)
    old = c.cookies.get(COOKIE_NAME)
    assert c.post("/api/auth/password", json={"current": "123", "new": "corta"}).status_code == 400
    r = c.post("/api/auth/password", json={"current": "123", "new": "una-password-lunga"})
    assert r.status_code == 200
    assert c.get("/api/auth/me").json()["initial_password"] is False  # nuovo cookie valido
    c.cookies.set(COOKIE_NAME, old)
    assert c.get("/api/runs").status_code == 401  # vecchia sessione revocata
    assert login(c, pw="123").status_code == 401
    assert login(c, pw="una-password-lunga").status_code == 200


def test_logout_clears_cookie(client):
    c, _ = client
    login(c)
    c.post("/api/auth/logout")
    assert c.get("/api/runs").status_code == 401


def test_security_headers(client):
    c, _ = client
    r = c.get("/api/auth/me")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
