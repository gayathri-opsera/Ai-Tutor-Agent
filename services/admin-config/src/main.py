from fastapi import FastAPI
from src.api.config import router
from src.service import AdminConfigService

app = FastAPI(title="Admin Config")
app.include_router(router)

@app.on_event("startup")
async def startup():
    app.state.admin_config = AdminConfigService()

app.state.admin_config = AdminConfigService()

@app.get("/health")
async def health():
    return {"status": "healthy"}
