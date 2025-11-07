# Spotify Metadata Integration Implementation

This document describes the implementation of three key requirements for downloaded files in the Music Downloader application.

## Requirements Implemented

1. **File modification date corresponds to playlist addition date**
2. **GROUPING tag (TIT1) contains release date in YYYY-MM-DD format**
3. **File image corresponds to Spotify cover**

## Implementation Details

### 1. File Timestamps

**Location**: `backend/app/utils/downloader.py` - `_set_file_timestamps()` function

The file modification time is set to the most recent `added_at` date from the track's playlist memberships:

```python
async def _set_file_timestamps(file_path: Path, track: Track, track_id: int) -> None:
    """Set file timestamps based on track metadata and playlist context.
    
    Creation time: Track release_date (if available), otherwise current time
    Modification time: Most recent added_at from playlists (if available), otherwise current time
    """
```

**Behavior**:
- Queries all `PlaylistTrack` entries for the track
- Uses the most recent `added_at` timestamp as modification time
- Sets creation time to track's `release_date` (when available)
- Falls back to current time if metadata is unavailable
- Cross-platform support (Windows, macOS, Linux)

**Called**: Automatically after each download in `perform_download()`

### 2. GROUPING Tag with Release Date

**Location**: `backend/app/utils/downloader.py` - metadata args in `perform_download()`

The release date is embedded as a metadata tag during the download process:

```python
# Add release date metadata
if track.release_date:
    release_date_str = track.release_date.strftime("%Y-%m-%d")
    release_year = track.release_date.strftime("%Y")
    # GROUPING tag with full date (YYYY-MM-DD)
    pp_args.append(f"-metadata grouping={_q(release_date_str)}")  # generic/m4a
    pp_args.append(f"-metadata TIT1={_q(release_date_str)}")      # ID3v2 (mp3)
    # Year/Date tags
    pp_args.append(f"-metadata date={_q(release_date_str)}")      # ISO date (generic)
    pp_args.append(f"-metadata year={_q(release_year)}")          # year (generic)
    pp_args.append(f"-metadata TDRC={_q(release_date_str)}")      # ID3v2 recording time
    pp_args.append(f"-metadata TYER={_q(release_year)}")          # ID3v2 year (legacy)
```

**Behavior**:
- Formats release date as `YYYY-MM-DD` (e.g., "2023-06-15")
- Extracts year as `YYYY` (e.g., "2023")
- Writes to multiple tags for maximum compatibility:
  - **GROUPING/TIT1**: Full date for organization and filtering
  - **date**: ISO date for modern players
  - **year**: Year only for basic compatibility
  - **TDRC**: ID3v2.4 recording time (MP3)
  - **TYER**: ID3v2.3 year for legacy MP3 players
- Applied via ffmpeg post-processing arguments during yt-dlp download
- Only added if `track.release_date` is available

**Tags Used**:
- `TIT1`: ID3v2 tag for MP3 files (Content Group Description) - contains full date
- `grouping`: Generic tag for M4A and other formats - contains full date
- `date`: Generic ISO date tag
- `year`: Generic year tag
- `TDRC`: ID3v2.4 recording time
- `TYER`: ID3v2.3 year (legacy compatibility)

### 3. Spotify Cover Embedding

**Location**: `backend/app/utils/downloader.py` - `_download_spotify_cover()` and `_embed_cover_image()` functions

Spotify album covers are prioritized over YouTube thumbnails:

```python
async def _download_spotify_cover(cover_url: str, temp_dir: Path) -> Optional[Path]:
    """Download Spotify cover image to a temporary file and return the path."""
    
async def _embed_cover_image(audio_file: Path, cover_file: Path, ffmpeg_path: str) -> bool:
    """Embed cover image into audio file using ffmpeg."""
```

**Workflow**:
1. After download completes, check if track has a Spotify cover URL (`https://i.scdn.co/...`)
2. If present, disable YouTube thumbnail embedding
3. Download the Spotify cover image via HTTP
4. Use ffmpeg to embed the cover into the audio file
5. Clean up temporary cover file
6. Recalculate file checksum after embedding

**Behavior**:
- Spotify covers are detected by URL pattern: `https://i.scdn.co/`
- Downloads cover asynchronously using httpx
- Supports JPEG and PNG formats
- Creates temporary output file, then replaces original
- Handles both MP3 (`-id3v2_version 3`) and M4A (`-disposition:v:0 attached_pic`) formats
- Falls back gracefully if cover download or embedding fails

**Environment Control**:
- `DOWNLOAD_EMBED_THUMBNAIL=1` (default): Enables cover embedding
- When Spotify cover is available, YouTube thumbnail is skipped

## Code Changes

### Modified Files

1. **`backend/app/utils/downloader.py`**:
   - Added `_download_spotify_cover()` function
   - Added `_embed_cover_image()` function
   - Modified metadata args to include GROUPING/TIT1 tags
   - Added Spotify cover detection and embedding logic
   - File timestamps already implemented (existing feature)

2. **`backend/tests/test_spotify_cover_and_metadata.py`** (NEW):
   - Test for file modification timestamp matching playlist added_at
   - Test for metadata args construction with release date
   - Validates integration with fake downloads

3. **`README.md`**:
   - Updated documentation with new metadata and cover features

## Testing

Two test cases validate the implementation:

1. **`test_download_with_spotify_cover_and_metadata`**:
   - Creates a complete scenario with playlist, track, and download
   - Verifies file modification time matches `added_at` date (±2 seconds tolerance)
   - Confirms file is created with proper metadata

2. **`test_grouping_tag_in_metadata_args`**:
   - Tests metadata construction for tracks with release dates
   - Validates download completes without errors

All existing tests continue to pass, confirming backward compatibility.

## Dependencies

- **httpx**: For downloading Spotify cover images (already in requirements)
- **ffmpeg**: For embedding covers and writing metadata (already required)
- **pywin32** (Windows only): For setting creation time on Windows (optional)

## Limitations and Future Enhancements

1. **Tag Verification**: Current tests verify the logic but don't read ID3 tags. Could add `mutagen` library to verify tags in integration tests.

2. **Cover Quality**: Currently uses the first available Spotify image URL. Could prioritize by size/quality.

3. **Error Handling**: Failures in cover download or embedding don't fail the overall download - they log and continue.

4. **Fake Mode**: Fake downloads create placeholder files but don't embed actual covers (httpx calls would work but are skipped for simplicity).

## Summary

All three requirements are fully implemented:

✅ **File modification date** = Most recent playlist `added_at` timestamp  
✅ **GROUPING tag (TIT1)** = Release date in `YYYY-MM-DD` format  
✅ **File image** = Spotify cover (with YouTube thumbnail fallback)

The implementation integrates seamlessly with the existing download workflow, maintains backward compatibility, and follows the project's architecture patterns.
