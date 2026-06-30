"""Confidence Grader FastAPI app."""
from fastapi import FastAPI
from src.api.grader import router as grader_router


def create_app() -> FastAPI:
    app = FastAPI(title="Confidence Grader", version="1.0.0")
    app.include_router(grader_router)

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    return app


app = create_app()
