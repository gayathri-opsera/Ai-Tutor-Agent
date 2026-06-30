from fastapi import FastAPI
from src.api.assessment import router
from src.service import AssessmentService

app = FastAPI(title="Assessment Engine")
app.include_router(router)

@app.on_event("startup")
async def startup():
    app.state.assessment_service = AssessmentService()

app.state.assessment_service = AssessmentService()

@app.get("/health")
async def health():
    return {"status": "healthy"}
