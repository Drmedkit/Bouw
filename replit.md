# Bouw — Tobias Bouw Portfolio

## Overview
Single-file portfolio site for Tobias Bouw showcasing web design and AI automation services. All HTML, CSS, and JS live in one `index.html` file (~2500 lines). Python/Flask backend serves the static file and provides two AI-powered API endpoints.

## Architecture
- **Frontend**: Single `index.html` with inline CSS + JS
- **Backend**: Flask server (`server.py`) on port 5000
- **AI**: Anthropic Claude via Replit AI Integrations (no API key needed)
- **Fonts**: Google Fonts via CDN
- **Images**: Unsplash CDN
- **Deployment**: Autoscale with gunicorn

## Project Structure
```
index.html    — The entire site (HTML + CSS + JS inline)
server.py     — Flask backend with /api/design and /api/chat endpoints
CONTEXT.md    — Detailed project documentation
replit.md     — This file
```

## API Endpoints

### POST /api/design
Generates a custom CSS style theme from a text description.
- Request: `{ "prompt": "cozy coffee shop with warm tones" }`
- Response: Style JSON object matching the styles[] schema
- Model: claude-haiku-4-5 (fast, lightweight)

### POST /api/chat
Conversational lead capture that generates full HTML preview pages.
- Request: `{ "messages": [{ "role": "user"|"bot", "text": "..." }] }`
- Response: `{ "reply": "...", "lead": {...}, "page": null | "<!DOCTYPE html>..." }`
- Model: claude-sonnet-4-5 (balanced performance)

## Key Features
- 12 swipeable CSS themes
- Industry demo takeover (Restaurant, Nightclub, E-commerce)
- AI Design Prompt — "Can't find your vibe?" generates custom themes via /api/design
- Chat lead capture — "Ready to build yours?" conversational flow via /api/chat
- Fallback deterministic chat flow when API is unavailable

## Running
- Workflow: `python server.py` (Flask dev server on port 5000)
- Deployment: `gunicorn --bind=0.0.0.0:5000 --reuse-port --workers=2 server:app`
