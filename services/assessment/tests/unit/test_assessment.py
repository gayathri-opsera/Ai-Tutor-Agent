import pytest
from httpx import ASGITransport, AsyncClient
from src.main import app
from src.service import AssessmentService, AssessmentType

def test_score_calculation():
    svc = AssessmentService()
    qid = "q1"
    a = svc.create("Test", AssessmentType.PRE, [{"text": "Q?", "options": ["A","B"], "correct_index": 0}])
    qid = a.questions[0].id
    result = svc.submit(a.id, {qid: 0})
    assert result["score"] == 1.0

@pytest.mark.asyncio
async def test_assessment_api():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/v1/assessments", json={
            "title": "Pre Test", "assessment_type": "pre",
            "questions": [{"text": "2+2?", "options": ["3","4"], "correct_index": 1}]
        })
        assert resp.status_code == 200
