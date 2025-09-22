from __future__ import annotations

from typing import Any, Dict
import logging


def get_uvicorn_log_config(level: int | str = logging.INFO) -> Dict[str, Any]:
    """Return a logging dictConfig for uvicorn and app loggers with time included.

    - Time format: HH:MM:SS
    - Applies to uvicorn error/access logs and our backend.* loggers.
    """
    # Normalize level
    if isinstance(level, str):
        try:
            level = getattr(logging, level.upper())
        except Exception:
            level = logging.INFO

    time_format = "%H:%M:%S"
    # Use uvicorn's color-capable formatters, but include timestamps.
    default_fmt = "%(asctime)s %(levelprefix)s [%(name)s] %(message)s"
    access_fmt = "%(asctime)s %(levelprefix)s %(client_addr)s - \"%(request_line)s\" %(status_code)s"

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "()": "uvicorn.logging.DefaultFormatter",
                "fmt": default_fmt,
                "datefmt": time_format,
                "use_colors": True,
            },
            "access": {
                "()": "uvicorn.logging.AccessFormatter",
                "fmt": access_fmt,
                "datefmt": time_format,
                "use_colors": True,
            },
        },
        "handlers": {
            "default": {
                "class": "logging.StreamHandler",
                "formatter": "default",
                "level": level,
                "stream": "ext://sys.stdout",
            },
            "access": {
                "class": "logging.StreamHandler",
                "formatter": "access",
                "level": level,
                "stream": "ext://sys.stdout",
            },
        },
        "loggers": {
            # Uvicorn loggers
            "uvicorn": {"handlers": ["default"], "level": level, "propagate": False},
            "uvicorn.error": {"handlers": ["default"], "level": level, "propagate": False},
            "uvicorn.access": {"handlers": ["access"], "level": level, "propagate": False},
            # Our app loggers
            "backend": {"handlers": ["default"], "level": level, "propagate": False},
            "backend.app": {"handlers": ["default"], "level": level, "propagate": False},
        },
        "root": {"handlers": ["default"], "level": level},
    }
