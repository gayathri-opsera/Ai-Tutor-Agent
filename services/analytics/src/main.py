from fastapi import FastAPI
from src.api.analytics import router
from src.service import AnalyticsService

app = FastAPI(title="Analytics")
app.include_router(router)

@app.on_event("startup")
async def startup():
    app.state.analytics = AnalyticsService()

app.state.analytics = AnalyticsService()

@app.get("/health")
async def health():
    return {"status": "healthy"}
