# Bouw — Tobias Bouw Portfolio

## Overview
Single-file portfolio site for Tobias Bouw showcasing web design and AI automation services. All HTML, CSS, and JS live in one `index.html` file (~2800 lines). Python/Flask backend serves the static file and provides AI-powered API endpoints.

## Architecture
- **Frontend**: Single `index.html` with inline CSS + JS
- **Backend**: Flask server (`server.py`) on port 5000
- **AI**: All AI powered by xAI Grok 4.1 Fast via user's own API key
  - Chat: `grok-4-1-fast-non-reasoning` — context-aware conversational responses
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
Context-aware conversational lead capture using fast AI model.
- Request: `{ "messages": [...], "lead": {...}, "context": { "entryPoint": "work_with_me|cta|demo_restaurant|...", "activeStyle": "Midnight Studio", "customPrompt": "", "device": "mobile|desktop" } }`
- Response: `{ "reply": "...", "lead": {...}, "buildTriggered": bool, "jobId": "..." }`
- Model: grok-4-1-fast-non-reasoning
- First call (empty messages) generates a context-aware greeting based on entry point, style viewed, custom prompt, and device
- When lead has business + type + vibe + email → triggers background page build

### GET /api/chat/status/<job_id>
Poll for background page build status.
- Response: `{ "status": "building"|"done"|"error", "page": "...html..." }`

### POST /api/chat/continue
Continue chat after build is triggered (same model, keeps gathering details, passes context).

### GET /api/leads
Returns all leads from the database (most recent first, max 100). Includes phone and entry_context.

## Database Schema
```sql
leads (
    id SERIAL PRIMARY KEY,
    job_id VARCHAR(64) UNIQUE,
    business, type, vibe, email, name, phone,
    tagline, colors, services, audience, features,
    page_html TEXT,
    status VARCHAR(32) DEFAULT 'building',
    entry_context TEXT DEFAULT '',
    created_at TIMESTAMP, updated_at TIMESTAMP
)
```

## Chat Context System
- **Entry points** pass context to chatOpen(): `work_with_me` (top nav), `cta` (bottom CTA), `demo_restaurant/nightclub/ecommerce` (industry demos)
- **Context object** sent to API: `{ entryPoint, activeStyle, customPrompt, device }`
- **AI adapts greeting** based on context: references the demo they viewed, the style they liked, or their custom design prompt
- **Escape routes**: WhatsApp button (wa.me/31618072754, prominent on mobile) and email link (tobiassteltnl@gmail.com) always visible in chat UI
- **WhatsApp pre-fill** includes the style they were viewing

## Chat Flow (Parallel Architecture)
1. Visitor opens chat from any entry point → context captured (style, entry point, device)
2. AI generates personalized greeting based on context
3. AI asks for business name FIRST — this is the trigger
4. As soon as business name is captured → background build starts immediately (page + images in parallel)
5. Chat continues gathering type, vibe, email, name, phone, extras — all while build runs
6. Build uses ThreadPoolExecutor: page HTML and custom images (grok-2-image) generate simultaneously
7. Images are injected into page HTML after both complete (Unsplash URLs replaced with custom ones)
8. Preview shown only after BOTH email is collected AND build is done
9. Visitors who don't want to chat can use WhatsApp or email escape routes

## Contact Info (for chat escape routes)
- WhatsApp: +31 6 18072754
- Email: tobiassteltnl@gmail.com

## Environment Variables
- `XAI_API_KEY` — User's xAI API key for Grok models
- `DATABASE_URL` — Auto-set by Replit PostgreSQL

## Running
- Workflow: `python server.py` (Flask dev server on port 5000)
- Deployment: `gunicorn --bind=0.0.0.0:5000 --reuse-port --workers=2 --timeout=120 server:app`

## Key Features
- 12 swipeable CSS themes with desktop style rail
- Desktop cursor tutorial (ghost cursor clicks rail dot on first visit)
- Mobile hand swipe tutorial on first visit
- Industry demo takeover (Restaurant, Nightclub, E-commerce)
- AI Design Prompt integrated in intro section — generates custom themes via /api/design
- Context-aware chat lead capture — stealth website builder
- WhatsApp + email escape routes in chat for visitors who prefer direct contact
- Phone number collection through natural conversation
- Fallback deterministic chat flow when API is unavailable
- All leads stored in PostgreSQL with full profile + entry context
