"""Test the in-memory log buffer functionality."""
import pytest


def test_log_buffer_basic_operations():
    """Test basic log buffer append and retrieval."""
    from backend.app.utils.log_buffer import LogBuffer
    
    buf = LogBuffer(max_lines=10)
    
    # Initially empty
    assert len(buf) == 0
    assert buf.get_lines() == []
    
    # Add some logs
    buf.info("Message 1")
    buf.warning("Message 2")
    buf.error("Message 3")
    buf.debug("Message 4")
    
    assert len(buf) == 4
    lines = buf.get_lines()
    assert len(lines) == 4
    assert "[INFO] Message 1" in lines[0]
    assert "[WARN] Message 2" in lines[1]
    assert "[ERROR] Message 3" in lines[2]
    assert "[DEBUG] Message 4" in lines[3]


def test_log_buffer_circular_behavior():
    """Test that buffer is circular and discards old entries."""
    from backend.app.utils.log_buffer import LogBuffer
    
    buf = LogBuffer(max_lines=3)
    
    buf.info("First")
    buf.info("Second")
    buf.info("Third")
    buf.info("Fourth")
    buf.info("Fifth")
    
    # Should only have the last 3
    assert len(buf) == 3
    lines = buf.get_lines()
    assert "Third" in lines[0]
    assert "Fourth" in lines[1]
    assert "Fifth" in lines[2]


def test_log_buffer_max_lines_adjustment():
    """Test changing max_lines dynamically."""
    from backend.app.utils.log_buffer import LogBuffer
    
    buf = LogBuffer(max_lines=20)
    for i in range(20):
        buf.info(f"Message {i}")
    
    assert len(buf) == 20
    
    # Reduce max lines - this should truncate old entries
    # Minimum is 10, so setting to 15 should give us 15
    buf.max_lines = 15
    assert buf.max_lines == 15
    assert len(buf) == 15
    
    # Should have kept the most recent entries (last 15: 5-19)
    lines = buf.get_lines()
    assert "Message 5" in lines[0]
    assert "Message 19" in lines[-1]
    
    # Setting below minimum should clamp to 10
    buf.max_lines = 3
    assert buf.max_lines == 10
    assert len(buf) == 10


def test_log_buffer_get_count():
    """Test getting a limited number of lines."""
    from backend.app.utils.log_buffer import LogBuffer
    
    buf = LogBuffer(max_lines=10)
    for i in range(5):
        buf.info(f"Message {i}")
    
    # Get all
    assert len(buf.get_lines()) == 5
    
    # Get last 2
    lines = buf.get_lines(count=2)
    assert len(lines) == 2
    assert "Message 3" in lines[0]
    assert "Message 4" in lines[1]


def test_log_buffer_clear():
    """Test clearing the buffer."""
    from backend.app.utils.log_buffer import LogBuffer
    
    buf = LogBuffer(max_lines=10)
    buf.info("Test")
    assert len(buf) == 1
    
    buf.clear()
    assert len(buf) == 0
    assert buf.get_lines() == []


def test_log_buffer_size_bytes():
    """Test size estimation."""
    from backend.app.utils.log_buffer import LogBuffer
    
    buf = LogBuffer(max_lines=10)
    assert buf.size_bytes() == 0
    
    buf.info("Hello World")
    size = buf.size_bytes()
    assert size > 0
    # Should include level + message length + some overhead
    assert size >= len("INFO") + len("Hello World")


def test_log_buffer_entries():
    """Test getting raw entries."""
    from backend.app.utils.log_buffer import LogBuffer
    
    buf = LogBuffer(max_lines=10)
    buf.info("Test message")
    
    entries = buf.get_entries()
    assert len(entries) == 1
    assert entries[0].level == "INFO"
    assert entries[0].message == "Test message"
    assert entries[0].timestamp is not None


def test_global_download_logs_singleton():
    """Test that the global download_logs singleton exists."""
    from backend.app.utils.log_buffer import download_logs
    
    # Should be a LogBuffer instance
    assert download_logs is not None
    assert hasattr(download_logs, 'append')
    assert hasattr(download_logs, 'get_lines')
