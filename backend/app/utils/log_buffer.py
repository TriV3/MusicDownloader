"""
In-memory log buffer for download worker logs.

Keeps the last N log lines in memory with configurable size.
Provides thread-safe append and retrieval operations.
"""
from __future__ import annotations

import os
import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional


@dataclass
class LogEntry:
    timestamp: datetime
    level: str
    message: str
    
    def format(self) -> str:
        ts = self.timestamp.strftime("%H:%M:%S")
        return f"[{ts}] [{self.level}] {self.message}"


class LogBuffer:
    """Thread-safe circular buffer for log entries."""
    
    def __init__(self, max_lines: int = 200) -> None:
        self._max_lines = max_lines
        self._buffer: deque[LogEntry] = deque(maxlen=max_lines)
        self._lock = threading.Lock()
    
    @property
    def max_lines(self) -> int:
        return self._max_lines
    
    @max_lines.setter
    def max_lines(self, value: int) -> None:
        with self._lock:
            # Clamp value between 10 and 5000
            self._max_lines = max(10, min(5000, value))
            # Create new deque with updated maxlen, preserving recent entries
            new_buffer: deque[LogEntry] = deque(maxlen=self._max_lines)
            new_buffer.extend(self._buffer)
            self._buffer = new_buffer
    
    def append(self, level: str, message: str) -> None:
        """Add a log entry to the buffer."""
        entry = LogEntry(
            timestamp=datetime.utcnow(),
            level=level.upper(),
            message=message
        )
        with self._lock:
            self._buffer.append(entry)
    
    def info(self, message: str) -> None:
        self.append("INFO", message)
    
    def warning(self, message: str) -> None:
        self.append("WARN", message)
    
    def error(self, message: str) -> None:
        self.append("ERROR", message)
    
    def debug(self, message: str) -> None:
        self.append("DEBUG", message)
    
    def get_lines(self, count: Optional[int] = None) -> List[str]:
        """Get formatted log lines, most recent last."""
        with self._lock:
            entries = list(self._buffer)
        if count is not None:
            entries = entries[-count:]
        return [e.format() for e in entries]
    
    def get_entries(self, count: Optional[int] = None) -> List[LogEntry]:
        """Get raw log entries, most recent last."""
        with self._lock:
            entries = list(self._buffer)
        if count is not None:
            entries = entries[-count:]
        return entries
    
    def clear(self) -> None:
        """Clear all log entries."""
        with self._lock:
            self._buffer.clear()
    
    def size_bytes(self) -> int:
        """Estimate the size of the log buffer in bytes."""
        with self._lock:
            total = 0
            for entry in self._buffer:
                # Rough estimate: timestamp (8 bytes) + level string + message
                total += 8 + len(entry.level) + len(entry.message)
            return total
    
    def __len__(self) -> int:
        with self._lock:
            return len(self._buffer)


# Default max lines from environment or 200
_default_max_lines = int(os.environ.get("LOG_BUFFER_MAX_LINES", "200"))

# Global singleton instance for download worker logs
download_logs = LogBuffer(max_lines=_default_max_lines)


# Custom logging handler to capture logs into the buffer
import logging


class LogBufferHandler(logging.Handler):
    """A logging handler that writes to the LogBuffer."""
    
    def __init__(self, buffer: LogBuffer, level: int = logging.INFO) -> None:
        super().__init__(level)
        self._buffer = buffer
    
    def emit(self, record: logging.LogRecord) -> None:
        try:
            # Map logging levels to our level names
            level_map = {
                logging.DEBUG: "DEBUG",
                logging.INFO: "INFO",
                logging.WARNING: "WARN",
                logging.ERROR: "ERROR",
                logging.CRITICAL: "ERROR",
            }
            level = level_map.get(record.levelno, "INFO")
            
            # Format the message with logger name for context
            msg = f"[{record.name}] {record.getMessage()}"
            self._buffer.append(level, msg)
        except Exception:
            # Don't let logging errors break the application
            pass


def install_log_capture(loggers: Optional[List[str]] = None, level: int = logging.INFO) -> None:
    """Install the log buffer handler on specified loggers.
    
    Args:
        loggers: List of logger names to capture. If None, captures root logger.
        level: Minimum log level to capture.
    """
    handler = LogBufferHandler(download_logs, level=level)
    handler.setFormatter(logging.Formatter("%(message)s"))
    
    if loggers is None:
        # Capture from root logger
        logging.getLogger().addHandler(handler)
    else:
        for name in loggers:
            logging.getLogger(name).addHandler(handler)
