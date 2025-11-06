# SPA Routing Implementation

## Problem

When deploying a Single Page Application (SPA) with FastAPI, direct URL access or OAuth redirects (like Spotify callback) would return a 404 error with `{"detail":"Not Found"}` instead of serving the frontend application.

This is a common issue with SPAs because:
1. The frontend uses client-side routing (React Router, Vue Router, etc.)
2. The server needs to serve `index.html` for all non-API routes
3. The client-side router then handles the actual routing based on the URL

## Solution

The solution involves implementing a proper fallback mechanism in FastAPI to serve `index.html` for all non-API routes while preserving API functionality.

### Implementation Details

1. **Static Assets Mount**: Static assets (JS, CSS, images) are mounted at `/assets` to ensure they are served correctly.

2. **SPA Fallback Route**: A catch-all route `/{full_path:path}` is defined to handle all other routes:
   - API routes (starting with `api/`) raise an HTTPException(404) to let FastAPI handle them properly
   - Static files in the root (e.g., `favicon.ico`) are served if they exist
   - All other routes serve `index.html` to let the frontend router handle them

3. **Route Order**: The catch-all route is defined after all API routes to ensure proper route matching priority.

### Code Structure

```python
static_dir = Path(__file__).resolve().parent / "static"
if static_dir.exists():
    # Serve static assets (JS, CSS, images, etc.)
    assets_dir = static_dir / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")
    
    # SPA fallback: serve index.html for all non-API routes
    from starlette.exceptions import HTTPException
    
    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        # Don't intercept API routes - let FastAPI handle them and return proper 404
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        
        # Check if the requested file exists in static_dir (e.g., favicon.ico, robots.txt)
        requested_file = static_dir / full_path
        if requested_file.is_file():
            return FileResponse(str(requested_file))
        
        # For all other routes, serve index.html to let the frontend router handle it
        index_file = static_dir / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        raise HTTPException(status_code=404, detail="Not Found")
```

### Benefits

- Direct URL access works (e.g., `https://example.com/library`)
- OAuth redirects work (e.g., `https://example.com/callback/spotify?code=...`)
- Browser refresh on any route works correctly
- API routes remain functional with proper 404 handling
- Static assets are served efficiently
- Root-level static files (favicon, robots.txt) are supported

### Testing

Comprehensive tests are included in `backend/tests/test_spa_routing.py` to ensure:
- SPA routes serve `index.html`
- API routes are not intercepted
- Static assets are served correctly
- Root-level static files are handled
- Documentation redirects work
- Non-existent API routes return proper 404

## Related Files

- `backend/app/main.py` - Main application with SPA fallback implementation
- `backend/tests/test_spa_routing.py` - Comprehensive test suite
- `frontend/vite.config.ts` - Vite configuration for building to `backend/app/static`
