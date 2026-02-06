# Bouw — Tobias Bouw Portfolio

## Overview
Single-file portfolio site for Tobias Bouw showcasing web design and AI automation services. All HTML, CSS, and JS live in one `index.html` file (~2500 lines). Python/Flask backend serves the static file and provides AI-powered API endpoints.

## Architecture
- **Frontend**: Single `index.html` with inline CSS + JS
- **Backend**: Flask server (`server.py`) on port 5000
- **AI**: All AI powered by xAI Grok 4.1 Fast via user's own API key
  - Chat: `grok-4-1-fast-non-reasoning` — instant conversational responses
  - Page Builder: `grok-4-1-fast` — generates full HTML pages in background thread
  - Design Themes: `grok-4-1-fast-non-reasoning` — generates CSS theme JSON
- **Database**: PostgreSQL (Replit built-in) — stores all leads with full details + generated pages
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
- Model: grok-4-1-fast-non-reasoning

### POST /api/chat
Conversational lead capture using fast AI model.
- Request: `{ "messages": [...], "lead": {...} }`
- Response: `{ "reply": "...", "lead": {...}, "buildTriggered": bool, "jobId": "..." }`
- Model: grok-4-1-fast-non-reasoning
- When lead has business + type + vibe + email → triggers background page build

### GET /api/chat/status/<job_id>
Poll for background page build status.
- Response: `{ "status": "building"|"done"|"error", "page": "...html..." }`

### POST /api/chat/continue
Continue chat after build is triggered (same model, keeps gathering details).

### GET /api/leads
Returns all leads from the database (most recent first, max 100).

## Database Schema
```sql
leads (
    id SERIAL PRIMARY KEY,
    job_id VARCHAR(64) UNIQUE,
    business, type, vibe, email, name, tagline, colors, services, audience, features,
    page_html TEXT,
    status VARCHAR(32) DEFAULT 'building',
    created_at TIMESTAMP, updated_at TIMESTAMP
)
```

## Chat Flow
1. Visitor opens chat → Grok 4.1 Fast responds instantly
2. AI gathers: business name, type, vibe, email, + extras (tagline, colors, services, audience, features)
3. Once minimum info collected + email → background build triggers (Grok 4.1 generates full HTML page)
4. Lead saved to database immediately when build starts
5. Frontend polls /api/chat/status — user keeps chatting via /api/chat/continue
6. Page ready → preview slides in, lead updated in database with generated HTML

## Environment Variables
- `XAI_API_KEY` — User's xAI API key for Grok models
- `DATABASE_URL` — Auto-set by Replit PostgreSQL

## Running
- Workflow: `python server.py` (Flask dev server on port 5000)
- Deployment: `gunicorn --bind=0.0.0.0:5000 --reuse-port --workers=2 --timeout=120 server:app`

## Key Features
- 12 swipeable CSS themes
- Industry demo takeover (Restaurant, Nightclub, E-commerce)
- AI Design Prompt — "Can't find your vibe?" generates custom themes via /api/design
- Chat lead capture — stealth website builder with instant email delivery
- Fallback deterministic chat flow when API is unavailable
- All leads stored in PostgreSQL for easy export/integration
