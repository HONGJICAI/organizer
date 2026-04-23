import hashlib
import hmac
import os

from fastapi import Depends, HTTPException, Query
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


def require_media_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    token: str | None = Query(default=None),
) -> None:
    """Auth for browser-loaded media (<img src>): accepts Bearer header or ?token= query param."""
    if ADMIN_PASSWORD is None:
        return
    expected = _make_token(ADMIN_PASSWORD)
    if credentials is not None and credentials.credentials == expected:
        return
    if token is not None and token == expected:
        return
    raise HTTPException(status_code=401, detail="Unauthorized")
