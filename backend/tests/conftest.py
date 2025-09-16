from pathlib import Path
import os
import sys
import pytest
import asyncio
import contextlib

# Improve asyncio behavior on Windows to reduce event-loop-closed noise
if sys.platform.startswith("win"):
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # type: ignore[attr-defined]
    except Exception:
        pass

# Ensure project root and backend paths are importable for tests
ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
APP = BACKEND / "app"

for p in (str(ROOT), str(BACKEND), str(APP)):
    if p not in sys.path:
        sys.path.insert(0, p)

"""
Test configuration

We use a shared in-memory SQLite database so multiple SQLAlchemy connections
(engine.begin(), sessions, etc.) see the same schema/data during the test run.
This relies on the SQLite URI form with mode=memory & cache=shared.
"""
# Shared in-memory DB across connections
os.environ.setdefault(
    "DATABASE_URL",
    "sqlite+aiosqlite:///file:memdb1?mode=memory&cache=shared&uri=true",
)
os.environ.setdefault("DISABLE_DOWNLOAD_WORKER", "1")


@pytest.fixture(scope="session", autouse=True)
async def _startup_and_shutdown_app():
    """Ensure FastAPI startup/shutdown events run once per test session.

    This creates all tables on startup as defined in app.main.on_startup.
    """
    try:
        from backend.app.main import app  # type: ignore
    except Exception:  # pragma: no cover
        from app.main import app  # type: ignore

    # Starlette exposes startup/shutdown helpers via the router
    await app.router.startup()
    yield
    # Ensure in-process worker is stopped before shutting down the app to avoid pending tasks
    try:
        try:
            from backend.app.worker import downloads_worker as dw  # type: ignore
        except Exception:  # pragma: no cover
            from app.worker import downloads_worker as dw  # type: ignore
        if dw.download_queue:
            try:
                await dw.download_queue.wait_idle(timeout=1.0)
            except Exception:
                pass
            try:
                await dw.download_queue.stop()
            except Exception:
                pass
            dw.download_queue = None
            # Allow cancellation callbacks to flush before loop shutdown
            try:
                await asyncio.sleep(0.05)
            except Exception:
                pass
    finally:
        await app.router.shutdown()


@pytest.fixture(autouse=True)
async def _ensure_worker_stopped_after_each_test():
    """Ensure that if any test started the worker, it is stopped before the next test.

    This prevents lingering background tasks that can cause noisy asyncio warnings
    on Windows or during loop teardown.
    """
    yield
    try:
        try:
            from backend.app.worker import downloads_worker as dw  # type: ignore
        except Exception:  # pragma: no cover
            from app.worker import downloads_worker as dw  # type: ignore
        if dw.download_queue:
            try:
                await dw.download_queue.wait_idle(timeout=0.5)
            except Exception:
                pass
            try:
                await dw.download_queue.stop()
            except Exception:
                pass
            dw.download_queue = None
            # allow callbacks to drain
            with contextlib.suppress(Exception):
                await asyncio.sleep(0.02)
    except Exception:
        pass
