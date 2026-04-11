import pytest
import json
import os
from pathlib import Path
from unittest.mock import patch, MagicMock
from click.testing import CliRunner

from cloudmesh.ai.command.speedtest import (
    speedtest_group, 
    get_path_size_mb, 
    format_hms
)

@pytest.fixture
def runner():
    return CliRunner()

@pytest.fixture
def mock_history_path(tmp_path, monkeypatch):
    """Mocks the history file path to a temporary directory."""
    fake_config = tmp_path / "speedtest.json"
    monkeypatch.setattr("cloudmesh.ai.command.speedtest.get_history_path", lambda: fake_config)
    return fake_config

# --- Helper Function Tests ---

def test_format_hms():
    assert format_hms(0) == "0s"
    assert format_hms(45) == "45s"
    assert format_hms(61) == "1m 1s"
    assert format_hms(3600) == "1h"
    assert format_hms(3661) == "1h 1m 1s"
    assert format_hms(7321) == "2h 2m 1s"

def test_get_path_size_mb(tmp_path):
    # Test file
    f = tmp_path / "test.bin"
    f.write_bytes(b"0" * 1024 * 1024 * 2) # 2MB
    assert get_path_size_mb(str(f)) == 2.0

    # Test directory
    d = tmp_path / "test_dir"
    d.mkdir()
    (d / "f1.bin").write_bytes(b"0" * 1024 * 1024 * 1) # 1MB
    (d / "f2.bin").write_bytes(b"0" * 1024 * 1024 * 1) # 1MB
    assert get_path_size_mb(str(d)) == 2.0

    # Test non-existent
    assert get_path_size_mb("/tmp/non_existent_path_12345") == 0

# --- Command Tests ---

def test_run_command_success(runner, mock_history_path):
    """Test that 'run' command calculates speed and saves to history."""
    with patch("subprocess.run") as mock_run, \
         patch("cloudmesh.ai.command.speedtest.generate_fast_dummy_file"):
        
        # Mock subprocess.run to return success for both transfer and cleanup
        mock_run.return_value = MagicMock(returncode=0)
        
        result = runner.invoke(speedtest_group, ["run", "my-host", "--size", "10"])
        
        assert result.exit_code == 0
        assert "Throughput" in result.output
        assert mock_history_path.exists()
        
        # Verify history content
        with open(mock_history_path, "r") as f:
            history = json.load(f)
            assert "my-host:scp" in history
            assert history["my-host:scp"]["method"] == "scp"

def test_run_command_failure(runner, mock_history_path):
    """Test that 'run' command handles subprocess errors."""
    with patch("subprocess.run") as mock_run, \
         patch("cloudmesh.ai.command.speedtest.generate_fast_dummy_file"):
        
        # Simulate a failure (e.g., SSH timeout)
        mock_run.side_effect = Exception("SSH Connection Timeout")
        
        result = runner.invoke(speedtest_group, ["run", "bad-host"])
        
        assert "Execution failed: SSH Connection Timeout" in result.output

def test_predict_command_no_history(runner, mock_history_path):
    """Test prediction fails gracefully when no history exists."""
    # Ensure file doesn't exist
    if mock_history_path.exists():
        mock_history_path.unlink()
        
    result = runner.invoke(speedtest_group, ["predict", "my-host", "--path", "."])
    assert "No history found" in result.output

def test_predict_command_missing_host(runner, mock_history_path):
    """Test prediction fails when host is not in history."""
    history_data = {"other-host:scp": {"speed_mbytes": 10.0}}
    mock_history_path.write_text(json.dumps(history_data))
    
    result = runner.invoke(speedtest_group, ["predict", "my-host", "--path", "."])
    assert "No recorded speed for 'my-host' using scp" in result.output

def test_predict_command_success(runner, mock_history_path, tmp_path):
    """Test prediction calculation based on mocked history."""
    # Pre-populate history: 10 MB/s
    history_data = {
        "my-host:scp": {"speed_mbytes": 10.0, "method": "scp"}
    }
    mock_history_path.write_text(json.dumps(history_data))
    
    # Create a dummy file of 5MB
    test_dir = tmp_path / "test_data"
    test_dir.mkdir()
    (test_dir / "file.bin").write_bytes(b"0" * 1024 * 1024 * 5)
    
    result = runner.invoke(speedtest_group, ["predict", "my-host", "--path", str(test_dir)])
    
    assert result.exit_code == 0
    assert "Total Size" in result.output
    assert "5.00 MB" in result.output
    # 5MB / 10MB/s = 0.5s
    assert "0.50s" in result.output
