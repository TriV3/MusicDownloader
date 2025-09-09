from pathlib import Path
import os
import sys
import pytest

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
    await app.router.shutdown()
