"""Migration script to drop deprecated Spotify audio feature columns from tracks table.

SQLite before 3.35 does not support DROP COLUMN directly; we use a table
recreation strategy that preserves data for remaining columns.

Columns removed:
    danceability, energy, tempo, musical_key, loudness, mode,
    speechiness, acousticness, instrumentalness, liveness, valence

Usage:
    (Activate your virtualenv)
    python -m backend.app.db.migrations.remove_audio_features

The script is idempotent: if columns are already gone it exits quickly.
"""
from __future__ import annotations
import sqlite3
from pathlib import Path
import sys

DB_PATH = Path(__file__).resolve().parents[4] / "music.db"

REMOVED_COLUMNS = {
    "danceability",
    "energy",
    "tempo",
    "musical_key",
    "loudness",
    "mode",
    "speechiness",
    "acousticness",
    "instrumentalness",
    "liveness",
    "valence",
}

KEEP_COLUMNS_ORDER = [
    "id",
    "title",
    "artists",
    "album",
    "duration_ms",
    "isrc",
    "year",
    "explicit",
    "cover_url",
    "normalized_title",
    "normalized_artists",
    "genre",
    "bpm",
    "created_at",
    "updated_at",
]

def main():
    if not DB_PATH.exists():
        print(f"[migration] DB file not found: {DB_PATH}")
        return 1
    conn = sqlite3.connect(str(DB_PATH))
    try:
        cur = conn.execute("PRAGMA table_info(tracks)")
        cols = [r[1] for r in cur.fetchall()]
        present_removed = [c for c in cols if c in REMOVED_COLUMNS]
        if not present_removed:
            print("[migration] No deprecated audio feature columns present. Nothing to do.")
            return 0
        print(f"[migration] Will drop columns: {', '.join(present_removed)}")
        # Build create statement for temp table
        # Extract types from existing schema
        col_types = {}
        cur = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='tracks'")
        row = cur.fetchone()
        if not row or not row[0]:
            print("[migration] Could not retrieve original CREATE TABLE for tracks")
            return 2
        create_sql = row[0]
        # Very simple parse: lines between parentheses
        import re
        body = create_sql.split('(', 1)[1].rsplit(')', 1)[0]
        for line in body.split(','):
            line = line.strip()
            if not line or line.upper().startswith('CONSTRAINT'):
                continue
            parts = line.split()
            name = parts[0].strip('`"')
            if name in cols:
                col_types[name] = ' '.join(parts[1:])
        # Build column defs for kept columns that still exist
        col_defs = []
        for c in KEEP_COLUMNS_ORDER:
            if c not in col_types:
                print(f"[migration] WARNING: expected column {c} missing in existing schema; skipping")
                continue
            col_defs.append(f"{c} {col_types[c]}")
        create_temp = f"CREATE TABLE tracks_new (\n  {', '.join(col_defs)}\n)"
        print("[migration] Creating new table without deprecated columns ...")
        conn.execute("BEGIN")
        conn.execute(create_temp)
        keep_cols_clause = ', '.join([c for c in KEEP_COLUMNS_ORDER if c in col_types])
        conn.execute(f"INSERT INTO tracks_new ({keep_cols_clause}) SELECT {keep_cols_clause} FROM tracks")
        conn.execute("ALTER TABLE tracks RENAME TO tracks_old")
        conn.execute("ALTER TABLE tracks_new RENAME TO tracks")
        conn.execute("DROP TABLE tracks_old")
        conn.commit()
        print("[migration] Completed successfully.")
    except Exception as e:
        conn.rollback()
        print(f"[migration] ERROR: {e}")
        return 3
    finally:
        conn.close()
    return 0

if __name__ == "__main__":
    sys.exit(main())
