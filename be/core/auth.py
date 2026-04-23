import hashlib
import hmac
import os

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

ADMIN_PASSWORD: str | None = os.environ.get("ADMIN_PASSWORD")


def _make_token(password: str) -> str:
    return hmac.new(password.encode(), b"organizer", hashlib.sha256).hexdigest()


def create_token(password: str) -> str | None:
    if ADMIN_PASSWORD is None or password != ADMIN_PASSWORD:
        return None
    return _make_token(ADMIN_PASSWORD)


_bearer = HTTPBearer(auto_error=False)


def require_auth(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> None:
    if ADMIN_PASSWORD is None:
        return
    if credentials is None or credentials.credentials != _make_token(ADMIN_PASSWORD):
        raise HTTPException(status_code=401, detail="Unauthorized")
