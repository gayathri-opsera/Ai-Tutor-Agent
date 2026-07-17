"""Confidence Grader FastAPI app."""
from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from src.api.grader import router as grader_router
from libs.auth.src.service_middleware import ServiceAuthMiddleware  # bundled via Dockerfile COPY libs/


def create_app() -> FastAPI:
    app = FastAPI(title="Confidence Grader", version="1.0.0")
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(ServiceAuthMiddleware)
    app.include_router(grader_router)

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    return app


app = create_app()
