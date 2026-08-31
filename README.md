# Shrey Text Sharing

A deliberately small private web page for copying text between devices. It also supports short-lived file sharing. There is no database: text and uploaded files are intentionally cleared whenever the free Render service restarts or spins down.

## Security model

- The password and Flask session secret come from environment variables; neither is committed. Production refuses passwords shorter than 16 characters.
- HTTP routes, downloads, and real-time Socket.IO connections require an authenticated session.
- Socket.IO uses same-origin checks, uploads are limited to 10 MB and an allowlist of extensions, and shared text is limited to 100,000 characters.
- Render terminates TLS and the production session cookie is HTTPS-only.

## Run locally

```bash
cd copy-paste-fetaure/backend
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
AUTH_PASSWORD="choose-a-password" SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')" .venv/bin/python app.py
```

Open [http://localhost:5000](http://localhost:5000).

## Test

```bash
cd copy-paste-fetaure/backend
.venv/bin/python -m pip install pytest pytest-cov
AUTH_PASSWORD=test-password-long-enough SECRET_KEY=test-secret-key-that-is-long-enough \
  .venv/bin/python -m pytest --cov=app --cov-fail-under=80
```

## Deploy free on Render

The repository includes `render.yaml` for one free Docker web service in Singapore. Render generates the session secret. During first deployment, provide only `AUTH_PASSWORD` when prompted.

The local root `.env` is ignored by Git and provides empty slots for `RENDER_API_KEY`, `AUTH_PASSWORD`, and an optional local `SECRET_KEY`.

Free Render services sleep after 15 minutes without traffic and have an ephemeral filesystem. The first request after sleep can take about a minute, and any text or uploaded files are lost after a restart. That matches this temporary copy-and-paste use case.

## Why password auth instead of Google Sign-In

Google OAuth can be used without a paid database and an existing Google Cloud project can be reused. However, the deployed callback URL must be added exactly to that OAuth client, an OAuth consent screen and allowed account still need configuration, and the app would gain another dependency plus a client secret. For this one-person utility, a strong Render-only password is the smaller free solution. Google Sign-In can be added later if multiple people need separate accounts.
