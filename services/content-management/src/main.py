from fastapi import FastAPI
from src.api.content import router
from src.service import ContentManagementService

app = FastAPI(title="Content Management")
app.include_router(router)

@app.on_event("startup")
async def startup():
    app.state.cms = ContentManagementService()

app.state.cms = ContentManagementService()

@app.get("/health")
async def health():
    return {"status": "healthy"}
