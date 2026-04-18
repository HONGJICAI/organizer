"""Main FastAPI application entry point"""
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import SQLModel

import db
from api import comics, comicpage, videos, images, system
from core.lifespan import lifespan
from core.exceptions import http_exception_handler, validation_exception_handler
from core.openapi import custom_generate_unique_id, custom_openapi_schema

# Initialize FastAPI app
app = FastAPI(
    generate_unique_id_function=custom_generate_unique_id,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan
)

# Register exception handlers
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)

# Customize OpenAPI schema
app.openapi = lambda: custom_openapi_schema(app)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routers
app.include_router(comics.router)
app.include_router(comicpage.router)
app.include_router(videos.router)
app.include_router(images.router)
app.include_router(system.router)


if __name__ == "__main__":
    # Setup database
    SQLModel.metadata.create_all(db.engine)

    # Run the application
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
