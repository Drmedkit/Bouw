# Bouw — Tobias Bouw Portfolio

## Overview
Single-file portfolio site for Tobias Bouw showcasing web design and AI automation services. All HTML, CSS, and JS live in one `index.html` file (~2500 lines). Python/Flask backend serves the static file and provides AI-powered API endpoints.

## Architecture
- **Frontend**: Single `index.html` with inline CSS + JS
- **Backend**: Flask server (`server.py`) on port 5000
- **Chat AI**: Llama 3.3 70B via OpenRouter (Replit AI Integrations, no API key needed) — fast ~1s responses
- **Page Builder AI**: Claude Sonnet via Anthropic (Replit AI Integrations) — generates full HTML pages in background
- **Design AI**: Claude Haiku via Anthropic — generates CSS theme JSON
- **Email**: Resend integration for transactional emails (needs verified domain to work)
- **Fonts**: Google Fonts via CDN
- **Images**: Unsplash CDN
- **Deployment**: Autoscale with gunicorn

## Project Structure
```
index.html        — The entire site (HTML + CSS + JS inline)
server.py         — Flask backend with all API endpoints
requirements.txt  — Python dependencies
CONTEXT.md        — Detailed project documentation
replit.md         — This file
```

## API Endpoints

### POST /api/design
Generates a custom CSS style theme from a text description.
- Request: `{ "prompt": "cozy coffee shop" }`
- Response: Style JSON matching the styles[] schema
- Model: claude-haiku-4-5

### POST /api/chat
Conversational lead capture using fast AI model.
- Request: `{ "messages": [...], "lead": {...} }`
- Response: `{ "reply": "...", "lead": {...}, "buildTriggered": bool, "jobId": "..." }`
- Model: meta-llama/llama-3.3-70b-instruct via OpenRouter
- When lead has business + type + vibe + email → triggers background page build

### GET /api/chat/status/<job_id>
Poll for background page build status.
- Response: `{ "status": "building"|"done"|"error", "page": "...html..." }`

### POST /api/chat/continue
Continue chat after build is triggered (same model, keeps gathering details).

## Chat Flow
1. Visitor opens chat → Llama 3.3 responds instantly (~1s)
2. AI gathers: business name, type, vibe, email, + extras (tagline, colors, services, audience, features)
3. Once minimum info collected + email → background build triggers (Claude Sonnet generates full HTML page)
4. Frontend polls /api/chat/status — user keeps chatting via /api/chat/continue
5. Page ready → preview slides in + email sent to lead + notification to Tobias

## Email System (Resend)
- **Lead email**: Styled dark email with preview teaser, sent immediately when page is built
- **Tobias notification**: All lead details sent to TOBIAS_EMAIL env var
- **Note**: Requires verified domain in Resend dashboard (outlook.com won't work as sender)

## Environment Variables
- `AI_INTEGRATIONS_ANTHROPIC_API_KEY` / `AI_INTEGRATIONS_ANTHROPIC_BASE_URL` — auto-set
- `AI_INTEGRATIONS_OPENROUTER_API_KEY` / `AI_INTEGRATIONS_OPENROUTER_BASE_URL` — auto-set
- `TOBIAS_EMAIL` — Tobias's email for lead notifications (needs to be set)

## Running
- Workflow: `python server.py` (Flask dev server on port 5000)
- Deployment: `gunicorn --bind=0.0.0.0:5000 --reuse-port --workers=2 server:app`

## Key Features
- 12 swipeable CSS themes
- Industry demo takeover (Restaurant, Nightclub, E-commerce)
- AI Design Prompt — "Can't find your vibe?" generates custom themes via /api/design
- Chat lead capture — stealth website builder with instant email delivery
- Fallback deterministic chat flow when API is unavailable
