from fastapi import APIRouter, Request
router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])

@router.get("/summary")
async def get_summary(request: Request):
    svc = request.app.state.analytics
    return svc.summary()
