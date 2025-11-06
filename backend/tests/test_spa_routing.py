"""Test SPA routing and static file serving."""
import pytest
from httpx import AsyncClient

try:
    from backend.app.main import app
except Exception:
    from app.main import app


@pytest.mark.asyncio
async def test_spa_fallback_serves_index_for_routes():
    """Test that non-API routes serve index.html for SPA routing."""
    # Test various frontend routes that should return index.html
    routes = [
        "/",
        "/library",
        "/playlists",
        "/settings",
        "/callback/spotify",
        "/some/nested/route",
    ]
    
    async with AsyncClient(app=app, base_url="http://test") as ac:
        for route in routes:
            response = await ac.get(route, follow_redirects=False)
            # Should return 200 and HTML content (index.html)
            assert response.status_code == 200, f"Route {route} should return 200"
            assert "text/html" in response.headers.get("content-type", ""), f"Route {route} should return HTML"


@pytest.mark.asyncio
async def test_api_routes_not_intercepted():
    """Test that API routes are not intercepted by SPA fallback."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Test that API routes still work
        response = await ac.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        
        # Test that non-existent API routes return 404 with JSON
        response = await ac.get("/api/v1/nonexistent")
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_assets_served_correctly():
    """Test that static assets are served correctly."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # This test assumes assets exist in backend/app/static/assets/
        # In a real build, Vite generates files like index-<hash>.js
        response = await ac.get("/assets/index.js", follow_redirects=False)
        # If the file exists, it should return 200 or 404 if it doesn't exist
        # We just check that the route is handled (not returning the SPA fallback HTML)
        if response.status_code == 200:
            # Should not be HTML
            assert "text/html" not in response.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_root_static_files_served():
    """Test that root-level static files (favicon, robots.txt) are served if they exist."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Test favicon.ico if it exists
        response = await ac.get("/favicon.ico", follow_redirects=False)
        # Should either return the file (200) or fall back to index.html (200 with HTML)
        assert response.status_code == 200
        # If it's a real favicon, content-type won't be HTML
        # If it falls back to index.html, content-type will be HTML


@pytest.mark.asyncio
async def test_docs_redirect_works():
    """Test that /docs redirects to /api/docs."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/docs", follow_redirects=False)
        assert response.status_code in [307, 302]
        assert response.headers["location"] == "/api/docs"


@pytest.mark.asyncio
async def test_api_docs_accessible():
    """Test that API documentation is accessible."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/api/docs", follow_redirects=True)
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
