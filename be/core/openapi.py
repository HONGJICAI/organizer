"""OpenAPI schema customization"""
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.routing import APIRoute


def custom_generate_unique_id(route: APIRoute) -> str:
    """Generate unique IDs for OpenAPI routes"""
    return route.name.replace("CBV", "")

def custom_openapi_schema(app: FastAPI):
    """Customize OpenAPI schema to include error responses"""
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title="My API",
        version="1.0",
        routes=app.routes,
    )

    openapi_schema.setdefault("components", {}).setdefault("schemas", {})["MessageResponse"] = {
        "type": "object",
        "properties": {"msg": {"type": "string", "title": "Msg"}},
        "required": ["msg"],
        "title": "MessageResponse",
    }

    _msg_ref = {"$ref": "#/components/schemas/MessageResponse"}
    _error_codes = {
        "400": "Bad Request",
        "401": "Unauthorized",
        "404": "Not Found",
        "422": "Validation Error",
        "500": "Internal Server Error",
    }

    for path in openapi_schema["paths"].values():
        for method in path.values():
            method["responses"].update(
                {
                    code: {
                        "description": desc,
                        "content": {"application/json": {"schema": _msg_ref}},
                    }
                    for code, desc in _error_codes.items()
                }
            )

    app.openapi_schema = openapi_schema
    return app.openapi_schema
