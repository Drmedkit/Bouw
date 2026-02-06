# Bouw Project — Context Doc

## What is this?
Single-file portfolio site for **Tobias Bouw** (`index.html`) showcasing web design + AI automation services. Hosted at `github.com/Drmedkit/Bouw`.

## Architecture
- **One file**: `index.html` — all HTML, CSS, JS inline (~2500 lines)
- **No build tools**, no frameworks, no dependencies
- Google Fonts loaded via CDN, images via Unsplash CDN
- Local dev: `python3 -m http.server 8888` from `~/bouw` → `http://192.168.2.20:8888`

## Key Features

### 1. Swipeable Style Themes
- 12 distinct CSS themes in `styles[]` array (Midnight Studio, Brutalist, Haute Couture, Terminal, Glass, Neobrutalism, Zen, Synthwave, Memphis, Art Deco, Warm Analog, Candy Pop)
- `applyStyle(s)` applies a style object to all DOM elements
- Swipe left/right (touch + keyboard arrows) to switch themes
- Tutorial animation on first load shows the swipe gesture

### 2. Industry Demo Takeover
- 3 clickable mockup cards: **Restaurant** (La Maison), **Nightclub** (VOID), **E-commerce** (Maison Noir)
- Clicking a card calls `enterDemo(key)` which:
  - Saves all original content to `originalContent` object
  - Swaps ALL section content (label, headline, body, detail HTML)
  - Changes topbar name
  - Applies industry-specific style
  - Creates hero background image with gradient overlay
  - Shows back button + demo nav bar at bottom
- `exitDemo()` restores everything to original state
- Swiping during demo mode exits the demo

### 3. Demo Content Structure (per industry)
Each demo has 6 sections mapped to the portfolio sections:
- **#intro** → Hero with background image + CTA button
- **#websites** → Menu / Events / Collection (content showcase)
- **#automations** → **"Smart Systems"** — 4 automation feature cards in 2×2 grid
- **#stack** → **"What's Included"** — inline image + 4 deliverable feature cards
- **#approach** → Reservation form / Guestlist / Cart mockup
- **#cta** → "This could be your [business]. Built by Tobias Bouw."

### 4. Automation Features Showcased
**Restaurant**: Cancellation fee→coupon, SMS reminders, auto review requests, smart waitlist
**Nightclub**: Dynamic ticket pricing, capacity tracking, promoter dashboard, post-event flow
**E-commerce**: Abandoned cart recovery, low stock alerts, post-purchase flow, smart upsells

### 5. AI Design Prompt (Custom Style Generator)
- Section card with textarea for mood/style input
- Calls `/api/design` proxy (Replit backend — NOT YET BUILT)
- Replit backend should: receive `{ prompt }`, call OpenAI gpt-4o-mini, return a style JSON object matching the `styles[]` schema
- Generated style saved to `localStorage` as `tbouw_ai_custom_style`
- Swiping clears custom style

### 6. Chat Lead Capture + Personalized Demo
- **"Let's build yours →"** CTA button and **"Work with me"** topbar button open a **full-screen dark glass chat overlay**
- Chat tries `/api/chat` first (AI mode), falls back to deterministic flow when API unavailable
- **Deterministic fallback flow**: Name → Email → Business name → Type (quick-reply pills) → Vibe (quick-reply pills) → Progress bar → Demo
- **AI mode flow**: Free-form conversation with `/api/chat` endpoint. API returns `{ reply, lead, page }`. When `page` is returned, it's displayed in iframe.
- **Vibe → Style mapping**: Warm & Elegant → Haute Couture, Dark & Bold → Midnight Studio, Clean & Minimal → Zen, Loud & Electric → Synthwave, Playful & Fun → Candy Pop, Raw & Edgy → Neobrutalism
- **Type → Template mapping**: Restaurant/Nightclub/Online Store/Other → industry template
- After chat finishes, a **full standalone HTML page** is generated from the matched template + vibe style, stored in `localStorage` (`tbouw_preview_page`), and displayed in a **sandboxed iframe overlay**
- **"Love it? Let's talk →"** floating CTA appears over the iframe
- Lead data saved to `localStorage` (`tbouw_leads`) as JSON array
- `closeIframeDemo()` closes iframe and returns to portfolio

## `/api/chat` Endpoint (NOT YET BUILT)
Backend should be a thin proxy to an LLM (Claude/GPT). Expected contract:

```
POST /api/chat
Body: { "messages": [{ "role": "user"|"bot", "text": "..." }, ...] }

Response: {
  "reply": "Next bot message",
  "lead": { "name": "...", "email": "...", "business": "...", "type": "...", "vibe": "..." },
  "page": null | "<!DOCTYPE html>...full standalone HTML page..."
}
```

When `page` is non-null, the frontend stores it in localStorage and displays it in the iframe. The `lead` object is progressively filled as the conversation continues.

## Git Setup
- Repo: `~/bouw` → `github.com/Drmedkit/Bouw`
- SSH key: `~/.ssh/id_ed25519_github` (configured in `~/.ssh/config`)
- User: `Drmedkit` / `Drmedkit@users.noreply.github.com`

## Important Code Locations (approximate line numbers)
- **CSS**: lines 10–680 (themes, mockup cards, demo layouts, features grid, hero styles, full-screen chat, iframe overlay)
- **HTML body**: lines 680–960 (sections, mockup cards, designer, demo nav, full-screen chat overlay, iframe overlay)
- **styles[] array**: lines 980–1090 (12 theme objects)
- **applyStyle()**: lines 1130–1360 (applies theme to all elements)
- **industries object**: lines 1460–1700 (3 industry demo data)
- **enterDemo/exitDemo**: lines 1730–1920 (demo takeover logic)
- **applyDemoElements()**: lines 1810–1920 (styles dynamically created elements)
- **AI Designer**: lines 1930–2010 (generateDesign, resetDesign)
- **Chat + Iframe Demo**: lines 2030–2500 (full-screen chat, AI/fallback flow, page builder, iframe display, lead capture)

## TODO / Not Yet Done
- [ ] **Backend for `/api/chat`** — LLM proxy that has a conversation and generates full HTML pages
- [ ] **Replit backend** for AI design proxy (`/api/design` endpoint with OpenAI key)
- [ ] Domain setup / deployment beyond GitHub
- [ ] More polish on generated demo pages (richer templates, more sections)

## Style Schema (for AI designer backend)
```json
{
  "name": "string",
  "bg": "#hex or gradient",
  "fg": "#hex",
  "accent": "#hex",
  "cardBg": "rgba or #hex",
  "cardBorder": "CSS border or 'none'",
  "cardShadow": "CSS shadow (optional)",
  "cardBlur": "boolean (optional)",
  "cardGlow": "CSS shadow (optional)",
  "cardBorderLeft": "CSS border (optional)",
  "cardBorderTop": "CSS border (optional)",
  "labelFont": "font name from loaded fonts",
  "headlineFont": "font name",
  "headlineWeight": "number",
  "headlineSize": "clamp(...)",
  "headlineGradient": "CSS gradient (optional)",
  "bodyFont": "font name",
  "bodyColor": "#hex or rgba",
  "indicatorBg": "color",
  "indicatorFg": "color (optional)",
  "textAlign": "'center' (optional)",
  "overlay": "'none' | 'scanlines' | 'grid' | 'memphis'"
}
```

Available fonts: Syne, Fira Code, DM Serif Display, Familjen Grotesk, Instrument Serif, Noto Serif JP, Orbitron, Unbounded, Zilla Slab, Courier Prime
