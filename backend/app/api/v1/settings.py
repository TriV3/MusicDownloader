"""Settings API endpoints for managing application configuration."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pathlib import Path
import os
from typing import Optional

router = APIRouter(prefix="/settings", tags=["Settings"])


# Default cookies file path (inside container or local)
def _get_cookies_file_path() -> Path:
    """Get the path to the cookies file."""
    env_path = os.environ.get("YT_DLP_COOKIES_FILE")
    if env_path:
        return Path(env_path)
    # Default to /app/data/cookies.txt in container or ./data/cookies.txt locally
    data_dir = Path(os.environ.get("DATA_DIR", "/app/data"))
    return data_dir / "cookies.txt"


class CookiesStatus(BaseModel):
    """Response model for cookies status."""
    configured: bool
    file_path: str
    file_exists: bool
    file_size: Optional[int] = None
    line_count: Optional[int] = None


class CookiesUpload(BaseModel):
    """Request model for uploading cookies content."""
    content: str


@router.get("/cookies", response_model=CookiesStatus)
async def get_cookies_status():
    """Get the current status of YouTube cookies configuration."""
    cookies_path = _get_cookies_file_path()
    file_exists = cookies_path.exists()
    
    line_count = None
    file_size = None
    if file_exists:
        try:
            file_size = cookies_path.stat().st_size
            with open(cookies_path, "r", encoding="utf-8", errors="ignore") as f:
                line_count = sum(1 for line in f if line.strip() and not line.startswith("#"))
        except Exception:
            pass
    
    return CookiesStatus(
        configured=file_exists and (file_size or 0) > 0,
        file_path=str(cookies_path),
        file_exists=file_exists,
        file_size=file_size,
        line_count=line_count,
    )


@router.post("/cookies")
async def upload_cookies(body: CookiesUpload):
    """Upload YouTube cookies content (Netscape format).
    
    The content should be in Netscape cookies.txt format.
    You can export cookies from your browser using extensions like:
    - "Get cookies.txt LOCALLY" for Chrome/Firefox
    - "EditThisCookie" for Chrome
    """
    if not body.content or not body.content.strip():
        raise HTTPException(status_code=400, detail="Cookie content cannot be empty")
    
    cookies_path = _get_cookies_file_path()
    
    # Ensure parent directory exists
    cookies_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Validate basic format (should start with # or have tab-separated lines)
    lines = body.content.strip().split("\n")
    valid_lines = 0
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Netscape format: domain, flag, path, secure, expiration, name, value (tab-separated)
        parts = line.split("\t")
        if len(parts) >= 7:
            valid_lines += 1
    
    if valid_lines == 0:
        raise HTTPException(
            status_code=400, 
            detail="Invalid cookies format. Expected Netscape cookies.txt format with tab-separated fields."
        )
    
    # Write cookies file
    try:
        with open(cookies_path, "w", encoding="utf-8") as f:
            f.write(body.content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write cookies file: {e}")
    
    # Set environment variable for immediate use
    os.environ["YT_DLP_COOKIES_FILE"] = str(cookies_path)
    
    return {
        "success": True,
        "message": f"Cookies saved successfully ({valid_lines} cookie entries)",
        "file_path": str(cookies_path),
        "cookie_count": valid_lines,
    }


@router.delete("/cookies")
async def delete_cookies():
    """Delete the YouTube cookies file."""
    cookies_path = _get_cookies_file_path()
    
    if not cookies_path.exists():
        return {"success": True, "message": "No cookies file to delete"}
    
    try:
        cookies_path.unlink()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete cookies file: {e}")
    
    # Clear environment variable
    if "YT_DLP_COOKIES_FILE" in os.environ:
        del os.environ["YT_DLP_COOKIES_FILE"]
    
    return {"success": True, "message": "Cookies file deleted"}


@router.get("/cookies/preview")
async def preview_cookies():
    """Preview the first few lines of the cookies file (sanitized)."""
    cookies_path = _get_cookies_file_path()
    
    if not cookies_path.exists():
        raise HTTPException(status_code=404, detail="No cookies file found")
    
    try:
        with open(cookies_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()[:20]  # First 20 lines
        
        # Sanitize: show domain and cookie name but mask the value
        sanitized = []
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                sanitized.append(line)
                continue
            parts = line.split("\t")
            if len(parts) >= 7:
                # Mask the cookie value (last field)
                domain = parts[0]
                name = parts[5]
                value_preview = parts[6][:4] + "..." if len(parts[6]) > 4 else "***"
                sanitized.append(f"{domain}\t...\t{name}\t{value_preview}")
            else:
                sanitized.append("(invalid line)")
        
        return {"lines": sanitized, "total_lines": len(lines)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read cookies file: {e}")


@router.get("/cookies/check")
async def check_cookies():
    """Check if cookies file contains required YouTube authentication cookies."""
    cookies_path = _get_cookies_file_path()
    
    if not cookies_path.exists():
        return {
            "valid": False,
            "error": "No cookies file found",
            "found_cookies": [],
            "missing_cookies": ["__Secure-1PSID", "__Secure-3PSID", "LOGIN_INFO"],
        }
    
    # Required cookies for YouTube age-restricted content
    required_cookies = ["__Secure-1PSID", "__Secure-3PSID", "LOGIN_INFO"]
    important_cookies = ["SID", "HSID", "SSID", "APISID", "SAPISID"]
    
    found_required = []
    found_important = []
    all_cookie_names = []
    
    try:
        with open(cookies_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) >= 7:
                    cookie_name = parts[5]
                    all_cookie_names.append(cookie_name)
                    if cookie_name in required_cookies:
                        found_required.append(cookie_name)
                    if cookie_name in important_cookies:
                        found_important.append(cookie_name)
        
        missing_required = [c for c in required_cookies if c not in found_required]
        
        return {
            "valid": len(missing_required) == 0,
            "found_required": found_required,
            "found_important": found_important,
            "missing_required": missing_required,
            "total_cookies": len(all_cookie_names),
            "hint": "Missing __Secure-1PSID or LOGIN_INFO means the cookies won't authenticate. Re-export from browser while logged in." if missing_required else None,
        }
    except Exception as e:
        return {
            "valid": False,
            "error": str(e),
            "found_cookies": [],
            "missing_cookies": required_cookies,
        }


@router.post("/cookies/test")
async def test_cookies_with_ytdlp():
    """Test if cookies work by attempting to get video info for an age-restricted video."""
    import subprocess
    import shutil
    
    cookies_path = _get_cookies_file_path()
    
    if not cookies_path.exists():
        return {"success": False, "error": "No cookies file configured"}
    
    # Find yt-dlp
    ytdlp = shutil.which("yt-dlp")
    if not ytdlp:
        ytdlp = "/opt/venv/bin/yt-dlp"
    
    # Test with an age-restricted video (just get info, don't download)
    test_video = "https://www.youtube.com/watch?v=AnzL4GT_jFg"
    
    try:
        result = subprocess.run(
            [ytdlp, "--cookies", str(cookies_path), "--remote-components", "ejs:github", "--dump-json", "--no-download", test_video],
            capture_output=True,
            text=True,
            timeout=60,
        )
        
        if result.returncode == 0:
            return {
                "success": True,
                "message": "Cookies are working! Age-restricted videos can be downloaded.",
            }
        else:
            error = result.stderr or result.stdout
            if "Sign in to confirm your age" in error:
                return {
                    "success": False,
                    "error": "Cookies are not valid for authentication. Please re-export fresh cookies while logged into YouTube.",
                    "details": error[:500],
                }
            else:
                return {
                    "success": False,
                    "error": "yt-dlp test failed",
                    "details": error[:500],
                }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Test timed out"}
    except Exception as e:
        return {"success": False, "error": str(e)}

