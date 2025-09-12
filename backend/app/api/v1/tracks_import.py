from typing import Any, List, Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
import json
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

try:
    from ...db.session import get_session  # type: ignore
    from ...db.models.models import Track, TrackIdentity, SourceProvider  # type: ignore
    from ...utils.normalize import normalize_track  # type: ignore
except Exception:  # pragma: no cover
    from db.session import get_session  # type: ignore
    from db.models.models import Track, TrackIdentity, SourceProvider  # type: ignore
    from utils.normalize import normalize_track  # type: ignore

router = APIRouter(prefix="/tracks/import", tags=["tracks"])

# Expected English keys (primary) with fallback legacy French keys mapping for backward compatibility.
# Only artists and title are strictly required; genre/bpm/duration may be blank if unknown.
REQUIRED_KEYS = ["artists", "title"]
LEGACY_FR_MAP = {
    "Artiste": "artists",
    "Titre": "title",
    "Genre": "genre",
    "BPM": "bpm",
    "Durée": "duration",
}


def _parse_duration_str(s: Optional[str]) -> Optional[int]:
    if not s:
        return None
    if isinstance(s, (int, float)):
        # Already seconds maybe
        return int(float(s) * 1000)
    parts = str(s).strip().split(":")
    if len(parts) == 2 and all(p.isdigit() for p in parts):
        minutes, seconds = parts
        try:
            return (int(minutes) * 60 + int(seconds)) * 1000
        except Exception:
            return None
    return None


@router.post("/json")
async def import_tracks_json(
    file: UploadFile = File(..., description="JSON file containing an array of track objects with French keys"),
    dry_run: bool = Form(False, description="When true, does not persist changes; only returns preview."),
    session: AsyncSession = Depends(get_session),
):
    """Import tracks from a JSON file.

    Expected JSON shape: list[ { "artists": str, "title": str, "genre": str, "bpm": int|str, "duration": "m:ss"? } ]
    A track must provide genre and bpm (non-empty). bpm must be an integer > 0.
    Duplicate detection uses normalized (artists,title).
    """
    content = await file.read()
    try:
        data = json.loads(content.decode("utf-8"))
    except Exception as e:  # pragma: no cover - invalid JSON path
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")
    if not isinstance(data, list):
        raise HTTPException(status_code=400, detail="Root JSON must be an array")

    to_create: List[dict[str, Any]] = []
    errors: List[dict[str, Any]] = []

    for idx, raw in enumerate(data):
        if not isinstance(raw, dict):
            errors.append({"index": idx, "error": "Item is not an object"})
            continue
        # Transparent legacy conversion: if required english key absent but french key present, copy it.
        for fr_key, en_key in LEGACY_FR_MAP.items():
            if en_key not in raw and fr_key in raw:
                raw[en_key] = raw[fr_key]
        missing = [k for k in REQUIRED_KEYS if k not in raw or (isinstance(raw.get(k), str) and raw.get(k, "").strip() == "")]
        if missing:
            errors.append({"index": idx, "error": f"Missing required field(s): {', '.join(missing)}"})
            continue
        bpm_int: Optional[int] = None
        bpm_value = raw.get("bpm")
        if bpm_value not in (None, ""):
            try:
                if isinstance(bpm_value, (int, float)):
                    bpm_int = int(bpm_value)
                else:
                    bpm_int = int(str(bpm_value).strip())
                if bpm_int <= 0:
                    raise ValueError("BPM must be > 0")
            except Exception as e:  # pragma: no cover
                errors.append({"index": idx, "error": f"Invalid BPM: {e}"})
                continue

        duration_ms = _parse_duration_str(raw.get("duration"))
        mapped = {
            "artists": str(raw.get("artists")).strip(),
            "title": str(raw.get("title")).strip(),
            "genre": (str(raw.get("genre")).strip() or None) if raw.get("genre") is not None else None,
            "bpm": bpm_int,
            "duration_ms": duration_ms,
        }
        norm = normalize_track(mapped["artists"], mapped["title"])
        mapped["normalized_artists"] = norm.normalized_artists
        mapped["normalized_title"] = norm.normalized_title

        # Per-item duplicate check ensures we see committed rows from previous imports
        dup_query = await session.execute(
            select(Track.id).where(
                Track.normalized_artists == mapped["normalized_artists"],
                Track.normalized_title == mapped["normalized_title"],
            )
        )
        if dup_query.scalar_one_or_none() is not None:
            mapped["duplicate"] = True
        else:
            # Fallback: raw case-insensitive title/artists duplicate check
            raw_dup = await session.execute(
                select(Track.id).where(
                    func.lower(Track.artists) == mapped["artists"].lower(),
                    func.lower(Track.title) == mapped["title"].lower(),
                )
            )
            mapped["duplicate"] = raw_dup.scalar_one_or_none() is not None
        to_create.append(mapped)

    created_count = 0
    if not dry_run:
        for item in to_create:
            if item["duplicate"]:
                continue
            track = Track(**{k: v for k, v in item.items() if k != "duplicate"})
            session.add(track)
            await session.flush()
            identity = TrackIdentity(
                track_id=track.id,
                provider=SourceProvider.manual,
                provider_track_id=f"manual:{track.id}",
                provider_url=None,
            )
            session.add(identity)
            await session.flush()
            created_count += 1

    return {
        "dry_run": dry_run,
        "received": len(data),
        "valid": len(to_create),
        "errors": errors,
    "to_create_non_duplicates": sum(1 for i in to_create if not i["duplicate"]),
        "created": created_count,
        "items": to_create if dry_run else None,
    }
