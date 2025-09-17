# FAQ

Why is Swagger not at /docs?
- Docs are namespaced under `/api/docs` because the backend serves the SPA at `/`.
- Convenience redirects exist from `/docs` → `/api/docs`.

I see JSON at `/` instead of the app
- Ensure the frontend is built: `cd frontend && npm run build`.
- Check that `backend/app/static/index.html` exists.

CORS errors in dev
- Ensure the frontend uses relative `/api` paths and Vite proxy is configured.
- Verify backend CORS settings allow `http://localhost:5173`.

Database not found or tables missing
- The app creates tables on startup. Ensure the correct `DATABASE_URL` is used.
- For tests, an in-memory DB is configured via test fixtures.

Strict filter vs. showing all candidates
- When "Strict filter" is checked, only candidates with a display score ≥ 0.50 are shown (plus any already chosen candidate).
- When unchecked, there is no score limit: all candidates are listed so you can manually review.

Why does a YouTube search sometimes repeat?
- If no persisted candidates exist, the UI performs a one-off transient YouTube search to populate the table.
- To avoid hammering the backend in poor network conditions, a cooldown prevents repeated transient searches for 15 seconds, and an explicit "YouTube Search" action will refresh the list without triggering an immediate fallback.
- If yt-dlp frequently times out, consider increasing `YOUTUBE_SEARCH_TIMEOUT` or enabling `YOUTUBE_SEARCH_FALLBACK_FAKE=true` for development.
