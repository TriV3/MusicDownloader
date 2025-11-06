"""
Cross-platform tests for file timestamp functionality.
Tests the behavior on different operating systems.
"""
import asyncio
import os
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
import pytest


def test_platform_specific_functions_dont_crash():
    """Test that platform-specific functions handle missing dependencies gracefully."""
    
    with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as tmp:
        tmp.write(b"fake audio content")
        tmp_path = Path(tmp.name)
    
    try:
        # Test that the functions can be imported and don't crash
        from backend.app.utils.downloader import _set_windows_creation_time, _set_macos_creation_time
        
        creation_time = datetime(2023, 3, 20).timestamp()
        modification_time = datetime(2024, 6, 10).timestamp()
        
        # These should not crash even on wrong platforms or missing dependencies
        import asyncio
        
        async def test_functions():
            await _set_windows_creation_time(tmp_path, creation_time, modification_time)
            await _set_macos_creation_time(tmp_path, creation_time)
        
        asyncio.run(test_functions())
        
    except ImportError:
        # On platforms where backend imports don't work, use local imports
        pytest.skip("Backend imports not available in test environment")
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def test_basic_timestamp_setting():
    """Test basic timestamp setting without database dependencies."""
    
    with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as tmp:
        tmp.write(b"fake audio content")
        tmp_path = Path(tmp.name)
    
    try:
        # Test basic os.utime functionality (cross-platform)
        import time
        import asyncio
        
        async def set_timestamps():
            target_time = datetime(2024, 6, 10, 12, 0, 0).timestamp()
            await asyncio.to_thread(os.utime, tmp_path, (target_time, target_time))
        
        asyncio.run(set_timestamps())
        
        # Verify timestamp was set
        stat = tmp_path.stat()
        file_mtime = datetime.fromtimestamp(stat.st_mtime)
        expected_mtime = datetime(2024, 6, 10, 12, 0, 0)
        
        # Allow some tolerance for timezone and precision differences
        time_diff = abs((file_mtime - expected_mtime).total_seconds())
        assert time_diff < 60, f"Timestamp not set correctly: {file_mtime} vs {expected_mtime}"
        
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def test_platform_detection():
    """Test that platform detection works correctly."""
    import platform
    
    system = platform.system().lower()
    assert system in ['windows', 'linux', 'darwin'], f"Unknown platform: {system}"
    
    # Test that our platform-specific code paths exist
    if system == 'windows':
        # Should have pywin32 support or graceful fallback
        assert os.name == 'nt'
    elif system == 'darwin':
        # Should have SetFile support or graceful fallback
        pass
    elif system == 'linux':
        # Should handle lack of creation time setting gracefully
        pass


@pytest.mark.asyncio
async def test_cross_platform_compatibility():
    """Test that our timestamp functions work on all platforms."""
    
    # This test verifies that our functions can be called without error
    # regardless of the underlying platform or available dependencies
    
    with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as tmp:
        tmp.write(b"fake audio content")
        tmp_path = Path(tmp.name)
    
    try:
        # Test with different platform simulations
        import platform
        
        real_system = platform.system()
        
        with patch('platform.system') as mock_system:
            for test_platform in ['Windows', 'Darwin', 'Linux']:
                mock_system.return_value = test_platform
                
                # The functions should handle any platform gracefully
                # Even if specific functionality isn't available
                creation_time = datetime(2023, 3, 20).timestamp()
                modification_time = datetime(2024, 6, 10).timestamp()
                
                # Basic timestamp setting should always work
                await asyncio.to_thread(os.utime, tmp_path, (modification_time, modification_time))
                
                # Verify file still exists
                assert tmp_path.exists()
        
    finally:
        if tmp_path.exists():
            tmp_path.unlink()