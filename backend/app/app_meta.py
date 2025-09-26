"""Application metadata — single source of truth.

Keep human-friendly name here; semantic version is read from the project-level VERSION file.
"""

from pathlib import Path


def _load_version() -> str:
	"""Read the semantic version from the repository VERSION file."""
	version_file = Path(__file__).resolve().parents[2] / "VERSION"
	try:
		return version_file.read_text(encoding="utf-8").strip()
	except FileNotFoundError:  # pragma: no cover - only when repository is missing VERSION
		return "0.0.0"


__app_name__ = "Music Downloader API"
__version__ = _load_version()
