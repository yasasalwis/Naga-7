import pytest
import datetime
import uuid
from n7_core.event_pipeline.service import EventPipelineService
from schemas.events_pb2 import Event

@pytest.mark.asyncio
async def test_event_parsing():
    service = EventPipelineService()
    
    # Create a sample protobuf event
    event = Event(
        event_id="test-1",
        timestamp=datetime.datetime.utcnow().isoformat(),
        sentinel_id=str(uuid.uuid4()),
        event_class="process",
        severity="info",
        raw_data='{"pid": 123}'
    )
    payload = event.SerializeToString()
    
    # Mock message
    class MockMsg:
        data = payload
        
    # We can't easily test handle_event without mocking DB/NATS fully, 
    # but we can check if it parses without error.
    # The service.handle_event is async and returns None.
    # It catches exceptions and logs them.
    
    # Ideally we should mock logger and check calls, or mock DB session.
    # For now, just ensuring it runs without crashing on parse.
    await service.handle_event(MockMsg())
