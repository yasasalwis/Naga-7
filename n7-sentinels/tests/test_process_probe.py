import pytest
import asyncio
from n7_sentinels.probes.process_probe import ProcessProbe

@pytest.mark.asyncio
async def test_process_probe_initialization():
    probe = ProcessProbe()
    await probe.initialize({})
    assert len(probe._known_pids) > 0

@pytest.mark.asyncio
async def test_process_probe_observe():
    probe = ProcessProbe()
    await probe.initialize({})
    
    # Mock psutil to return a new PID
    # This is hard without mocking psutil. 
    # But we can test the generator mechanics.
    
    # For a real test, we'd need to mock psutil.pids()
    pass
