"""
Helper script to run the FastAPI app with a predictable sys.path on Windows.
Usage (cmd.exe):
  .venv\Scripts\python.exe run_api.py
"""
import os
import sys

from uvicorn import run

ROOT = os.path.dirname(os.path.abspath(__file__))
BACKEND_APP_DIR = os.path.join(ROOT, "backend", "app")

if BACKEND_APP_DIR not in sys.path:
  sys.path.insert(0, BACKEND_APP_DIR)

# Ensure reloader subprocess also sees our backend/app on PYTHONPATH
os.environ["PYTHONPATH"] = os.pathsep.join(
  [BACKEND_APP_DIR] + [p for p in os.environ.get("PYTHONPATH", "").split(os.pathsep) if p]
)

if __name__ == "__main__":
  # Run uvicorn with reload and limit watch dirs to backend/app for stability
  log_level = os.environ.get("APP_LOG_LEVEL", "info").lower()
  run(
    "backend.app.main:app",
    host="0.0.0.0",
    port=8000,
    reload=True,
    reload_dirs=[BACKEND_APP_DIR],
    log_level=log_level,
    access_log=True,
    # Set the working directory so relative file paths (like music.db) resolve at repo root
    # Note: uvicorn's run() doesn't take cwd, but our sys.path/PYTHONPATH adjustments above suffice
  )
