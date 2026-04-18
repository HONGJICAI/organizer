"""Exception handlers for the FastAPI application"""
from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from schemas.common import MessageResponse


async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions"""
    return JSONResponse(
        status_code=exc.status_code,
        content=MessageResponse(msg=exc.detail).model_dump(),
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors"""
    msg = ";".join([f'{error["input"]}: {error["msg"]}' for error in exc.errors()])
    return JSONResponse(
        status_code=400,
        content=MessageResponse(msg=msg).model_dump(),
    )


def abort(code: int, message: str = None):
    """Raise an HTTP exception with the given code and message"""
    raise HTTPException(status_code=code, detail=message)
