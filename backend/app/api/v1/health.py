from fastapi import APIRouter

try:
    from ...core.config import settings  # type: ignore
except Exception:  # pragma: no cover
    from core.config import settings  # type: ignore

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/info")
def info():
    """Return application info: name and version."""
    return {"name": settings.app_name, "version": settings.version}
