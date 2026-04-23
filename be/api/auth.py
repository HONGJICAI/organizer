from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import core.auth as auth_module

router = APIRouter()


class LoginRequest(BaseModel):
    password: str


class LoginResponse(BaseModel):
    token: str


class AuthStatusResponse(BaseModel):
    required: bool


@router.get("/api/auth/status", tags=["auth"])
def status() -> AuthStatusResponse:
    return AuthStatusResponse(required=auth_module.ADMIN_PASSWORD is not None)


@router.post("/api/auth/login", tags=["auth"])
def login(body: LoginRequest) -> LoginResponse:
    token = auth_module.create_token(body.password)
    if token is None:
        raise HTTPException(status_code=401, detail="Invalid password")
    return LoginResponse(token=token)
