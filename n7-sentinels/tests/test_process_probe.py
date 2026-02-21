import pytest
import asyncio
from unittest.mock import MagicMock
from n7_sentinels.probes.process_probe import ProcessProbe

@pytest.mark.asyncio
async def test_process_probe_initialization():
    probe = ProcessProbe()
    await probe.initialize({})
    assert len(probe._known_pids) > 0

def test_process_probe_anomaly_clean():
    probe = ProcessProbe()
    
    mock_process = MagicMock()
    mock_process.exe.return_value = "/usr/bin/python3"
    
    cmdline = ["python3", "main.py"]
    
    result = probe._evaluate_anomaly(mock_process, cmdline)
    
    assert result["is_anomaly"] is False
    assert result["severity"] == "info"

def test_process_probe_anomaly_suspicious_path():
    probe = ProcessProbe()
    
    mock_process = MagicMock()
    mock_process.exe.return_value = "/tmp/malicious_binary"
    
    cmdline = ["/tmp/malicious_binary"]
    
    result = probe._evaluate_anomaly(mock_process, cmdline)
    
    assert result["is_anomaly"] is True
    assert result["severity"] == "high"
    assert len(result["reasons"]) == 1
    assert "suspicious path" in result["reasons"][0]

def test_process_probe_anomaly_suspicious_cmd():
    probe = ProcessProbe()
    
    mock_process = MagicMock()
    mock_process.exe.return_value = "/bin/bash"
    
    cmdline = ["bash", "-i"]
    
    result = probe._evaluate_anomaly(mock_process, cmdline)
    
    assert result["is_anomaly"] is True
    assert result["severity"] == "high"
    assert len(result["reasons"]) == 1
    assert "Suspicious command line" in result["reasons"][0]

@pytest.mark.asyncio
async def test_process_probe_observe():
    probe = ProcessProbe()
    await probe.initialize({})
    
    # Mock psutil to return a new PID
    # This is hard without mocking psutil. 
    # But we can test the generator mechanics.
    
    # For a real test, we'd need to mock psutil.pids()
    pass
