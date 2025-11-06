# Cross-Platform File Timestamp Implementation

## Overview

The music downloader implements intelligent file timestamp management that sets meaningful dates based on Spotify metadata. This functionality is designed to work across different operating systems with platform-specific optimizations.

## Timestamp Strategy

When a track is downloaded, two timestamps are set based on Spotify data:

1. **File Creation Time**: Set to the track's Spotify release date (`album.release_date`)
2. **File Modification Time**: Set to the most recent playlist addition date (`added_at`)

This allows for chronological sorting and organization based on music history rather than download time.

## Platform Implementation

### Windows (Full Support)
- **Dependencies**: `pywin32` (optional, automatically installed on Windows)
- **Functionality**: 
  - ✅ Creation time setting via Windows API
  - ✅ Modification time setting via `os.utime()`
  - ✅ Full timestamp precision
- **Fallback**: If `pywin32` is not available, only modification time is set

### macOS (Partial Support)
- **Dependencies**: `SetFile` command (part of Xcode Command Line Tools)
- **Functionality**:
  - ✅ Creation time setting via `SetFile` command
  - ✅ Modification time setting via `os.utime()`
  - ⚠️ Requires Xcode Command Line Tools for creation time
- **Fallback**: If `SetFile` is not available, only modification time is set

### Linux (Basic Support)
- **Dependencies**: None required
- **Functionality**:
  - ❌ Creation time setting (filesystem-dependent, not easily controllable)
  - ✅ Modification time setting via `os.utime()`
  - ℹ️ Some filesystems (ext4, btrfs) support birth time but it's set at file creation
- **Behavior**: Relies on file creation happening at the right moment; only modification time is actively set

## Docker/Container Deployment

When running in Docker containers (typically Linux-based), the timestamp functionality adapts automatically:

```dockerfile
# The application automatically detects the Linux environment
# and uses the appropriate timestamp strategy
FROM python:3.11-slim
# ... (no special configuration needed)
```

### Container Considerations

1. **File System**: Container filesystems may not preserve all timestamp metadata when volumes are mounted
2. **Time Zones**: Ensure container time zone is set correctly for accurate timestamp interpretation
3. **Permissions**: Container user must have write permissions to set file timestamps

## Code Implementation

The cross-platform implementation uses a strategy pattern:

```python
async def _set_file_timestamps(file_path: Path, track: Track, track_id: int) -> None:
    """Cross-platform file timestamp setting."""
    
    # Always works on all platforms
    await asyncio.to_thread(os.utime, file_path, (modification_time, modification_time))
    
    # Platform-specific creation time handling
    system = platform.system().lower()
    
    if system == "windows":
        await _set_windows_creation_time(file_path, creation_time, modification_time)
    elif system == "darwin":
        await _set_macos_creation_time(file_path, creation_time)
    elif system == "linux":
        # Creation time is filesystem-dependent, no action needed
        pass
```

## Testing

Cross-platform compatibility is verified through automated tests:

```bash
# Run cross-platform compatibility tests
pytest backend/tests/test_file_timestamps_cross_platform.py -v
```

Tests cover:
- Platform detection
- Graceful fallback when dependencies are missing
- Basic timestamp setting functionality
- Error handling for permission issues

## Troubleshooting

### Windows Issues
- **Problem**: Creation time not being set
- **Solution**: Install `pywin32`: `pip install pywin32`
- **Verification**: Check that `import win32file` works

### macOS Issues
- **Problem**: Creation time not being set
- **Solution**: Install Xcode Command Line Tools: `xcode-select --install`
- **Verification**: Check that `SetFile` command is available

### Linux Issues
- **Problem**: Only modification time is set
- **Expected**: This is normal behavior on Linux
- **Alternative**: Use file organization based on modification time

### Container Issues
- **Problem**: Timestamps lost when container restarts
- **Solution**: Use proper volume mounts and ensure filesystem supports timestamps
- **Alternative**: Use bind mounts instead of named volumes for better timestamp preservation

## Performance Impact

- **Windows**: Minimal overhead for Windows API calls
- **macOS**: Small overhead for subprocess calls to `SetFile`
- **Linux**: No overhead (only standard `os.utime()` call)
- **All platforms**: Database query to get playlist addition dates (cached per download)

## Future Improvements

1. **Linux Enhancement**: Investigate `statx()` system call for better birth time support
2. **Container Optimization**: Explore volume mount options for better timestamp preservation
3. **Timezone Handling**: Improve timezone-aware timestamp conversion
4. **Metadata Fallbacks**: Use additional metadata sources when Spotify data is incomplete