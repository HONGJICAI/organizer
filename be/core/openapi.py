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

    for path in openapi_schema["paths"].values():
        for method in path.values():
            method["responses"].update(
                {
                    "400": {
                        "description": "Bad Request",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/MessageResponse"
                                }
                            }
                        },
                    },
                    "422": {
                        "description": "Validation Error",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/MessageResponse"
                                }
                            }
                        },
                    },
                }
            )

    app.openapi_schema = openapi_schema
    return app.openapi_schema
