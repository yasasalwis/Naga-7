import pytest
import asyncio
import json
from unittest.mock import patch, MagicMock, AsyncMock
from n7_sentinels.probes.osquery_probe import OsqueryProbe

@pytest.fixture
def mock_subprocess_exec():
    with patch('asyncio.create_subprocess_exec', new_callable=AsyncMock) as mock_exec:
        yield mock_exec

@pytest.mark.asyncio
async def test_osquery_probe_initialize_success(mock_subprocess_exec):
    probe = OsqueryProbe()
    
    mock_process = AsyncMock()
    mock_process.communicate.return_value = (b"osquery 5.12.2", b"")
    mock_process.returncode = 0
    mock_subprocess_exec.return_value = mock_process
    
    await probe.initialize({})
    
    mock_subprocess_exec.assert_called_once()

@pytest.mark.asyncio
async def test_osquery_probe_observe_matches(mock_subprocess_exec):
    probe = OsqueryProbe()
    
    # Mock finding a match
    mock_process = AsyncMock()
    mock_results = [{"pid": "1234", "name": "bad_actor", "path": "/tmp/bad", "cmdline": "/tmp/bad"}]
    mock_process.communicate.return_value = (json.dumps(mock_results).encode(), b"")
    mock_process.returncode = 0
    mock_subprocess_exec.return_value = mock_process
    
    # We need to manually iterate the async generator once, then break
    generator = probe.observe()
    
    event = await generator.__anext__()
    
    assert event["event_class"] == "osquery_anomaly"
    assert event["severity"] == "high"
    assert event["raw_data"]["results"]["pid"] == "1234"
    
    await probe.shutdown()
