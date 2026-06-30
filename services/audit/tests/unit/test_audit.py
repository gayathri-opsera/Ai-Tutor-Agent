import pytest
from src.logger import AuditLogger, audit_action

@pytest.mark.asyncio
async def test_audit_log():
    events = []
    async def publish(topic, payload):
        events.append(payload)
    logger = AuditLogger(publish=publish)
    entry = await logger.log("content.delete", "user1", "doc-1")
    assert entry.action == "content.delete"
    assert len(events) == 1

@pytest.mark.asyncio
async def test_audit_decorator():
    logger = AuditLogger()

    @audit_action("content.delete")
    async def delete_doc(audit_logger=None, user_id="u1", resource_id="d1"):
        return True

    await delete_doc(audit_logger=logger, user_id="u1", resource_id="d1")
    assert len(logger._store) == 1
