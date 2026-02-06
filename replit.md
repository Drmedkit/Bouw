# Bouw — Tobias Bouw Portfolio

## Overview
Single-file static portfolio site for Tobias Bouw showcasing web design and AI automation services. All HTML, CSS, and JS live in one `index.html` file (~2500 lines).

## Architecture
- **Static site**: No build tools, no frameworks, no dependencies
- **Serving**: Python3 HTTP server on port 5000
- **Fonts**: Google Fonts via CDN
- **Images**: Unsplash CDN
- **Deployment**: Static deployment from root directory

## Project Structure
```
index.html    — The entire site (HTML + CSS + JS inline)
CONTEXT.md    — Detailed project documentation
replit.md     — This file
```

## Key Features
- 12 swipeable CSS themes
- Industry demo takeover (Restaurant, Nightclub, E-commerce)
- AI Design Prompt section (backend not yet built)
- Chat lead capture with personalized demo generation

## Running
- Workflow: `python3 -m http.server 5000 --bind 0.0.0.0`
- Deployment: Static site from root directory
