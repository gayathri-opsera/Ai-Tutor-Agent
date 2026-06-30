from fastapi import FastAPI
from src.api.profile import router
from src.service import LearnerProfileService

app = FastAPI(title="Learner Profile")
app.include_router(router)

@app.on_event("startup")
async def startup():
    app.state.profile_service = LearnerProfileService()

app.state.profile_service = LearnerProfileService()

@app.get("/health")
async def health():
    return {"status": "healthy"}
