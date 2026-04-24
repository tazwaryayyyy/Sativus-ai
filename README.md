# Sativus AI

Sativus AI is a plant doctor and nature explorer built on a FastAPI backend with Groq-powered image analysis.

Point your camera at a plant or living organism to get multimodal analysis and care guidance.

## Why this project

- Plant care apps are often static and generic.
- Sativus makes diagnosis interactive, contextual, and conversational.
- The same interface supports both home gardening and outdoor exploration.

## Core features

- Plant Doctor mode: identify plant, assess health, and propose treatment steps.
- Nature Explorer mode: identify plants/animals/insects/fungi and provide facts.
- Live voice implementation removed; feature-flag scaffolding is kept for future provider integration.
- Reminder workflow: deterministic watering interval parsing with due-date storage.
- Journal memory: local history of scans for continuity in follow-up conversations.

## Tech stack

- Backend: FastAPI + WebSocket
- AI: Groq Vision API
- Frontend: Vanilla HTML/CSS/JS
- External APIs: Open-Meteo, iNaturalist

## Repository layout

```text
backend/main.py               # FastAPI app, analyze/reminders routes
frontend/index.html           # Full UI and client logic
frontend/manifest.json        # PWA manifest
frontend/sw.js                # Service worker
scripts/smoke_test.py         # REST smoke tests
scripts/live_stress_test.py   # Live scaffold check script
```

## Local setup

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Create backend env file from template and add key:

```env
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=llama-3.2-11b-vision-preview
LIVE_VOICE_ENABLED=false
LIVE_VOICE_PROVIDER=none
```

3. Start server from repository root:

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8080
```

4. Open app:

```text
http://localhost:8080
```

## Verification and stress testing

Basic smoke test:

```bash
python scripts/smoke_test.py
```

Live scaffold checks (optional):

```bash
# Windows PowerShell
$env:SATIVUS_ENABLE_LIVE_CHECKS=true
python scripts/run_pre_demo_checks.ps1
```

Health endpoint:

```text
GET /health
```

Metrics endpoint:

```text
GET /metrics
```

Includes:
- analyze requests, success/fail, average latency
- live sessions started/completed/failed

## Runtime behavior notes

- Analyze route is Groq-only in this version.
- Live voice route is scaffolded via `LIVE_VOICE_ENABLED` and `LIVE_VOICE_PROVIDER`.
  No provider implementation is included yet.
- API quota or malformed model outputs are handled and surfaced as safe responses.

## Production readiness

- Security headers middleware is enabled:
  `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, and `Strict-Transport-Security` (when `PROD` is set).
- Docker image includes a `/health` healthcheck.
- Analyze API now returns stricter status codes and sanitized error messages.

## Troubleshooting

- Port already in use on 8080:
  stop the existing process using that port, then restart uvicorn.
- No module named pylint:
  install it manually in the venv if you need lint checks.
- Live websocket errors under load:
  expected until a live provider implementation is added and enabled via feature flags.
- Frontend cannot connect:
  make sure you open http://localhost:8080 (not the html file directly).

## License

MIT License. See LICENSE.
