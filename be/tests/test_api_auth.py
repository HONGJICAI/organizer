import core.auth as auth_module


class TestStatus:
    def test_not_required_by_default(self, client):
        r = client.get("/api/auth/status")
        assert r.status_code == 200
        assert r.json() == {"required": False}

    def test_required_when_password_set(self, client, monkeypatch):
        monkeypatch.setattr(auth_module, "ADMIN_PASSWORD", "secret")
        r = client.get("/api/auth/status")
        assert r.status_code == 200
        assert r.json() == {"required": True}


class TestLogin:
    def test_login_fails_when_no_password_configured(self, client):
        r = client.post("/api/auth/login", json={"password": "anything"})
        assert r.status_code == 401

    def test_login_wrong_password(self, client, monkeypatch):
        monkeypatch.setattr(auth_module, "ADMIN_PASSWORD", "secret")
        r = client.post("/api/auth/login", json={"password": "wrong"})
        assert r.status_code == 401

    def test_login_correct_password_returns_token(self, client, monkeypatch):
        monkeypatch.setattr(auth_module, "ADMIN_PASSWORD", "secret")
        r = client.post("/api/auth/login", json={"password": "secret"})
        assert r.status_code == 200
        assert "token" in r.json()
        assert len(r.json()["token"]) == 64  # sha256 hex

    def test_token_is_deterministic(self, client, monkeypatch):
        monkeypatch.setattr(auth_module, "ADMIN_PASSWORD", "secret")
        r1 = client.post("/api/auth/login", json={"password": "secret"})
        r2 = client.post("/api/auth/login", json={"password": "secret"})
        assert r1.json()["token"] == r2.json()["token"]


class TestProtectedRoute:
    def test_accessible_when_no_password_configured(self, client):
        r = client.get("/api/comics")
        assert r.status_code == 200

    def test_blocked_when_password_set_and_no_token(self, client, monkeypatch):
        monkeypatch.setattr(auth_module, "ADMIN_PASSWORD", "secret")
        r = client.get("/api/comics")
        assert r.status_code == 401

    def test_accessible_with_valid_token(self, client, monkeypatch):
        monkeypatch.setattr(auth_module, "ADMIN_PASSWORD", "secret")
        login = client.post("/api/auth/login", json={"password": "secret"})
        token = login.json()["token"]
        r = client.get("/api/comics", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200

    def test_blocked_with_wrong_token(self, client, monkeypatch):
        monkeypatch.setattr(auth_module, "ADMIN_PASSWORD", "secret")
        r = client.get("/api/comics", headers={"Authorization": "Bearer badtoken"})
        assert r.status_code == 401
