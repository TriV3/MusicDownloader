# Getting Started (Windows)

This guide helps you run the app locally and explains the environment variables required for features like Spotify.

Prerequisites
- Windows with Python 3.10+ and Node.js 18+ installed.

1) Configure environment variables
- Copy the sample file and edit it:
	```
	cd d:\Dev\Projects\music_downloader
	copy backend\.env.example backend\.env
	```
- Open `backend/.env` in a text editor and set at least:
	- SECRET_KEY: a long random string (used to encrypt refresh tokens)
	- For Spotify integration (required if you will connect Spotify):
		- SPOTIFY_CLIENT_ID
		- SPOTIFY_CLIENT_SECRET
		- SPOTIFY_REDIRECT_URI (default: http://localhost:8000/api/v1/oauth/spotify/callback)
- Optional adjustments:
	- CORS_ORIGINS: keep defaults for local dev (http://localhost:5173,http://127.0.0.1:5173)
	- DATABASE_URL: default is SQLite at `./music.db`.

2) Start the backend (API)
```
cd d:\Dev\Projects\music_downloader
python -m venv .venv
.venv\Scripts\activate.bat
pip install -r backend\requirements.txt
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
or python run_api.py
```

3) Start the frontend (dev mode)
```
cd frontend
npm install
npm run dev
```
Open http://localhost:5173

Or build the frontend and let the backend serve it:
```
cd frontend
npm run build
```
Then open http://localhost:8000

Connect Spotify
1) Ensure Spotify env variables are set in `backend/.env` and the API is running.
2) Open the web app (http://localhost:5173 during dev, or http://localhost:8000 when built).
3) Navigate to the Playlists page and click “Connect to Spotify”.
4) Approve the permissions on Spotify’s website.
5) You’ll be redirected back to `/playlists`; the page shows “Connected to Spotify”. You can now Discover, Select, and Sync playlists.

Troubleshooting
- Missing Spotify configuration: set SPOTIFY_CLIENT_ID/SECRET/REDIRECT_URI in `backend/.env`, restart the API, and retry.
- API docs: http://localhost:8000/api/docs
- YouTube search stuck or empty results: set `YT_DLP_BIN` in `backend/.env` to your local yt-dlp (e.g., `.venv\Scripts\yt-dlp.exe` on Windows) and optionally lower `YOUTUBE_SEARCH_TIMEOUT` (default 8). For local demos, you can set `YOUTUBE_SEARCH_FAKE=1` or keep real search and enable `YOUTUBE_SEARCH_FALLBACK_FAKE=1` to get canned results when real search fails.

Track covers
- The tracks list shows cover thumbnails when available.
- If you persist YouTube search results for a track without a cover, the top result's thumbnail is used.
- Choosing a YouTube candidate also fills the cover if missing.
- You can also refresh the cover via the API: `POST /api/v1/tracks/{id}/cover/refresh`.

Downloads
- Use the "Ready to download" panel to quickly enqueue tracks that already have a chosen YouTube candidate.
- Toggle "Include downloaded" to also show tracks that were already downloaded if you want to re-download them.
- You can enqueue a download without typing numeric IDs: start typing a track title or artist in the search box and pick the result; the form will auto-fill the Track ID.
- Optionally, you can provide a specific Candidate ID if you want to override the chosen one.
