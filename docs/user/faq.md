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
