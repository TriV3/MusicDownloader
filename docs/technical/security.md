# Security

Secrets management
- Store secrets in environment variables or a secrets manager.
- Never commit secrets to git.
- Required env vars:
  - `SECRET_KEY` (used to encrypt refresh tokens)
  - `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`, `SPOTIFY_REDIRECT_URI`

Token storage
- Access tokens: short-lived, stored in DB for convenience.
- Refresh tokens: encrypted at rest using `SECRET_KEY` (Fernet-like scheme).
- Do not log tokens; redact sensitive values in logs and errors.

OAuth (Spotify)
- Use PKCE (code_verifier/code_challenge) + state for CSRF protection.
- Persist state + code_verifier until callback; validate then mark used.

CORS and origins
- Allow localhost dev origins during development.
- Restrict allowed origins in production.

Dependencies and updates
- Keep dependencies updated to receive security fixes.
- Run tests after upgrades; pin versions as needed.

Backups
- Database backups contain encrypted tokens; protect backups at rest.
