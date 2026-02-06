import os
import json
import re
import uuid
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import pg8000
from urllib.parse import urlparse
from flask import Flask, request, jsonify, send_from_directory
from openai import OpenAI
import gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__, static_folder=".", static_url_path="")

# xAI Grok client (OpenAI-compatible)
xai_client = OpenAI(
    api_key=os.environ.get("XAI_API_KEY"),
    base_url="https://api.x.ai/v1",
)

CHAT_MODEL = "grok-4-1-fast-non-reasoning"
BUILD_MODEL = "grok-4-1-fast"
DESIGN_MODEL = "grok-4-1-fast-non-reasoning"
IMAGE_MODEL = "grok-2-image"

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db():
    parsed = urlparse(DATABASE_URL)
    try:
        conn = pg8000.connect(
            host=parsed.hostname,
            port=parsed.port or 5432,
            user=parsed.username,
            password=parsed.password,
            database=parsed.path.lstrip("/"),
            ssl_context=True,
        )
    except Exception:
        conn = pg8000.connect(
            host=parsed.hostname,
            port=parsed.port or 5432,
            user=parsed.username,
            password=parsed.password,
            database=parsed.path.lstrip("/"),
            ssl_context=False,
        )
    conn.autocommit = True
    return conn

build_jobs = {}
build_lock = threading.Lock()

GOOGLE_SPREADSHEET_ID = os.environ.get("GOOGLE_SPREADSHEET_ID", "")
SHEET_HEADERS = ["Timestamp", "Job ID", "Status", "Business", "Type", "Vibe", "Email", "Name", "Phone", "Colors", "Tagline", "Services", "Audience", "Features", "Entry Context"]

def get_gsheet():
    sa_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    if not sa_json or not GOOGLE_SPREADSHEET_ID:
        return None
    try:
        sa_json = sa_json.strip()
        if not sa_json.endswith("}"):
            sa_json += "}"
        creds_dict = json.loads(sa_json)
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        gc = gspread.authorize(creds)
        return gc.open_by_key(GOOGLE_SPREADSHEET_ID).sheet1
    except Exception as e:
        print(f"[sheets] Error connecting to Google Sheets: {e}")
        return None

def sync_lead_to_sheet(job_id, lead, status="building", entry_context=""):
    try:
        sheet = get_gsheet()
        if not sheet:
            return
        existing = sheet.get_all_values()
        if not existing or existing[0] != SHEET_HEADERS:
            sheet.clear()
            sheet.append_row(SHEET_HEADERS)
            existing = [SHEET_HEADERS]

        row_data = [
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            job_id or "",
            status,
            lead.get("business", ""),
            lead.get("type", ""),
            lead.get("vibe", ""),
            lead.get("email", ""),
            lead.get("name", ""),
            lead.get("phone", ""),
            lead.get("colors", ""),
            lead.get("tagline", ""),
            lead.get("services", ""),
            lead.get("audience", ""),
            lead.get("features", ""),
            entry_context or "",
        ]

        row_idx = None
        for i, row in enumerate(existing):
            if len(row) > 1 and row[1] == job_id:
                row_idx = i + 1
                break

        if row_idx:
            sheet.update(f"A{row_idx}:O{row_idx}", [row_data])
            print(f"[sheets] Updated row {row_idx} for job {job_id}")
        else:
            sheet.append_row(row_data)
            print(f"[sheets] Added new row for job {job_id}")
    except Exception as e:
        print(f"[sheets] Error syncing to sheet: {e}")

AVAILABLE_FONTS = [
    "Syne", "Fira Code", "DM Serif Display", "Familjen Grotesk",
    "Instrument Serif", "Noto Serif JP", "Orbitron", "Unbounded",
    "Zilla Slab", "Courier Prime",
]

STYLE_SCHEMA_DESCRIPTION = """You are a web design expert. Generate a CSS style theme as a JSON object based on the user's description.

REQUIRED fields (you MUST include ALL of these):
{
  "name": "Short creative theme name (string)",
  "bg": "Background — hex like #0a0a0a OR CSS gradient like linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
  "fg": "Foreground/text color — hex like #ffffff",
  "accent": "Accent color — hex like #ff2975",
  "cardBg": "Card background — hex, rgba like rgba(255,255,255,0.1), or 'transparent'",
  "cardBorder": "CSS border like '1px solid rgba(255,255,255,0.1)' or 'none'",
  "cardBlur": false,
  "labelFont": "Font name from the allowed list below",
  "headlineFont": "Font name from the allowed list below",
  "headlineWeight": 700,
  "headlineSize": "clamp(1.8rem, 5vw, 3rem)",
  "bodyFont": "Font name from the allowed list below",
  "bodyColor": "Body text color — hex or rgba",
  "indicatorBg": "Toast indicator background color",
  "overlay": "MUST be one of: 'none', 'scanlines', 'grid', 'memphis'"
}

OPTIONAL fields (include only if they fit the mood):
- "cardShadow": "CSS box-shadow"
- "cardGlow": "CSS box-shadow for glow effect"
- "cardBorderLeft": "CSS left border accent"
- "cardBorderTop": "CSS top border accent"
- "headlineGradient": "CSS gradient for headline text"
- "indicatorFg": "Toast indicator text color"
- "textAlign": "'center' for zen/minimal vibes"

ALLOWED FONTS (ONLY use fonts from this list): """ + ", ".join(AVAILABLE_FONTS) + """

ALLOWED OVERLAY VALUES: none, scanlines, grid, memphis

Respond with ONLY the raw JSON object. No explanation, no markdown, no code fences."""


CHAT_SYSTEM_PROMPT = """You are Tobias Bouw's assistant. Your role is to gather requirements for a website preview. Be professional, clear, and direct.

ABSOLUTE RULE: NEVER use emojis. Not a single one. No exceptions. Write in plain text only.

CONVERSATION FLOW — Ask questions in this order (one at a time):

DESIGN ESSENTIALS — Collect these three fast, they drive the design:
1. business: Their business name ("What's your business called?")
2. type: Business category — accept whatever they say (restaurant, trades, consulting, etc.)
   - Ask: "What type of business is it?"
3. vibe: Design preference (Warm & Elegant, Dark & Bold, Clean & Minimal, Loud & Electric, Playful & Fun, Raw & Edgy)
   - Ask: "Which style direction fits? Warm & elegant, dark & bold, clean & minimal, loud & electric, playful & fun, or raw & edgy?"
   - If they're unsure: "Dark & bold works well for bars. Clean & minimal suits professional services."

Once you have business + type + vibe, the design is being created. Keep gathering the rest without mentioning it.

EMAIL — Required before we can show the preview:
4. email: Their email address ("What email should we send it to?")

ENRICHMENT — Gather while the design builds (nice-to-haves):
5. name: Their name ("What's your name?")
6. phone: Contact number ("Best number to reach you?")
7. colors: Brand colors ("Any specific brand colors?")
8. tagline: Business tagline ("Do you have a tagline or slogan?")
9. services: Key offerings ("What are your main products or services?")
10. audience: Target market ("Who's your target audience?")
11. features: Website features ("Any specific features? Booking, gallery, e-commerce?")

TONE & STYLE:
- Professional, calm, direct
- One question at a time
- Short acknowledgments: "Got it." "Noted." "Good choice."
- NEVER use emojis — not one
- No exclamation marks unless quoting the user
- If they skip optional fields, move on
- Brief design guidance when relevant: "Clean & minimal works well for that." "Dark tones suit nightlife."

HANDLING GENERAL QUESTIONS:
- Answer questions about Tobias's services directly
- Pricing: "Tobias provides custom quotes. Share your requirements and he'll follow up."
- Services: "Custom websites with design and automation. Restaurants, nightlife, e-commerce, and more."
- Contact: "You can reach Tobias at +31 6 18072754 or tobiassteltnl@gmail.com"
- After answering: "Want to see a preview built for your business?"

CRITICAL RULES:
- ZERO emojis in every response
- Ask ONE question at a time
- Keep responses under 2 sentences
- No excitement, no hype
- Professional acknowledgments only
- After getting email, continue gathering optional details
- Don't mention background processes or that anything is being built
- READ THE CONVERSATION HISTORY. If the user already said their business name, DO NOT ask again. Extract data from what they already told you.
- READ THE LEAD SUMMARY below. Any field listed there is DONE. Move to the next empty field.
- Always populate the lead JSON with everything you know from the conversation so far

{context_block}

{lead_summary}

Your response must ALWAYS be valid JSON with this structure:
{{
  "reply": "Your professional message to the user",
  "lead": {{
    "name": "their name or empty string",
    "email": "their email or empty string",
    "phone": "their phone number or empty string",
    "business": "business name or empty string",
    "type": "their business type as they described it, or empty string",
    "vibe": "Warm & Elegant|Dark & Bold|Clean & Minimal|Loud & Electric|Playful & Fun|Raw & Edgy or empty string",
    "tagline": "their tagline or empty string",
    "colors": "preferred colors or empty string",
    "services": "key services/products or empty string",
    "audience": "target audience or empty string",
    "features": "desired features or empty string"
  }}
}}

Remember: respond with ONLY the JSON object. No markdown, no code fences, no explanation outside the JSON."""


PAGE_BUILD_PROMPT = """You are a world-class web designer. Build a COMPLETE, STUNNING, standalone HTML page for this business:

Business: {business}
Type: {type}
Vibe/Style: {vibe}
Owner: {name}
Email: {email}
Tagline: {tagline}
Colors: {colors}
Services: {services}
Target Audience: {audience}
Features: {features}

Create a complete HTML page (<!DOCTYPE html> through </html>) that:
- Is FULLY self-contained with ALL CSS inline in a <style> tag
- Uses Google Fonts loaded via CDN <link> tags
- Has a stunning hero section with a background image (use Unsplash with ?w=1200&h=800&fit=crop)
- Has at least 4 distinct sections (hero, about/services, features/menu, CTA)
- Is fully mobile-responsive
- Matches the requested vibe perfectly
- Uses the business name throughout
- Includes the tagline if provided
- Includes their services/products if provided
- Looks like a real, professional website — not a template
- Has smooth scroll behavior
- Uses modern CSS (grid, flexbox, clamp, etc.)
- Has a sticky navigation bar
- Has hover effects and transitions
- Includes a footer with business info
- If tagline provided, use it as the hero subtitle

Pick Unsplash images that match their business:
- Restaurant: food, dining, kitchen images
- Nightclub / Bar: nightlife, cocktails, DJ images
- Online Store: products, lifestyle, shopping images
- Other: modern office, professional, workspace images

The page should look SO good that the client is blown away. This is a sales tool — it needs to impress.

Output ONLY the complete HTML. No explanations, no markdown, no code fences."""


def save_lead_to_db(job_id, lead, status="building", page_html=None, entry_context=""):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO leads (job_id, business, type, vibe, email, name, phone, tagline, colors, services, audience, features, page_html, status, entry_context)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (job_id) DO UPDATE SET
                business = EXCLUDED.business,
                type = EXCLUDED.type,
                vibe = EXCLUDED.vibe,
                email = EXCLUDED.email,
                name = EXCLUDED.name,
                phone = EXCLUDED.phone,
                tagline = EXCLUDED.tagline,
                colors = EXCLUDED.colors,
                services = EXCLUDED.services,
                audience = EXCLUDED.audience,
                features = EXCLUDED.features,
                page_html = EXCLUDED.page_html,
                status = EXCLUDED.status,
                entry_context = EXCLUDED.entry_context,
                updated_at = CURRENT_TIMESTAMP
        """, (
            job_id,
            lead.get("business", ""),
            lead.get("type", ""),
            lead.get("vibe", ""),
            lead.get("email", ""),
            lead.get("name", ""),
            lead.get("phone", ""),
            lead.get("tagline", ""),
            lead.get("colors", ""),
            lead.get("services", ""),
            lead.get("audience", ""),
            lead.get("features", ""),
            page_html,
            status,
            entry_context,
        ))
        conn.commit()
        cur.close()
        conn.close()
        print(f"[db] Lead saved: {job_id} ({status})")

        sync_thread = threading.Thread(
            target=sync_lead_to_sheet,
            args=(job_id, lead, status, entry_context),
            daemon=True
        )
        sync_thread.start()
    except Exception as e:
        print(f"[db] Error saving lead: {e}")


def generate_images_for_page(lead):
    business = lead.get("business", "Business")
    biz_type = lead.get("type", "business")
    vibe = lead.get("vibe", "modern")
    services = lead.get("services", "")
    tagline = lead.get("tagline", "")

    hero_prompt = f"Professional hero banner photo for a {biz_type} business called '{business}'. Style: {vibe}. {f'They offer: {services}.' if services else ''} High quality, wide landscape format, perfect for a website hero section. No text or logos in the image."
    secondary_prompt = f"Professional photo for a {biz_type} business website. {f'Showing: {services}.' if services else f'Style: {vibe}.'} Authentic, editorial quality. No text or logos."

    images = {}
    for key, prompt in [("hero", hero_prompt), ("secondary", secondary_prompt)]:
        try:
            response = xai_client.images.generate(
                model=IMAGE_MODEL,
                prompt=prompt,
                n=1,
                response_format="url",
            )
            url = response.data[0].url
            if url:
                images[key] = url
                print(f"[images] Generated {key} image for {business}")
        except Exception as e:
            print(f"[images] Failed to generate {key} image: {e}")

    return images


def _generate_page_html(lead):
    prompt = PAGE_BUILD_PROMPT.format(
        business=lead.get("business", "Business"),
        type=lead.get("type", "Other"),
        vibe=lead.get("vibe", "Clean & Minimal"),
        name=lead.get("name", ""),
        email=lead.get("email", ""),
        tagline=lead.get("tagline", ""),
        colors=lead.get("colors", ""),
        services=lead.get("services", ""),
        audience=lead.get("audience", ""),
        features=lead.get("features", ""),
    )
    response = xai_client.chat.completions.create(
        model=BUILD_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=8192,
    )
    html = response.choices[0].message.content or ""
    html = re.sub(r"^```(?:html)?\s*", "", html.strip())
    html = re.sub(r"\s*```$", "", html)
    if "<!DOCTYPE" not in html.upper():
        return None
    return html


def _inject_images_into_page(page_html, images):
    if not page_html or not images:
        return page_html
    hero_url = images.get("hero", "")
    secondary_url = images.get("secondary", "")
    img_pattern = re.compile(r"https://images\.unsplash\.com/[^\s\"')\]>]+")
    if hero_url:
        page_html = img_pattern.sub(hero_url, page_html, count=1)
    if secondary_url:
        matches = list(img_pattern.finditer(page_html))
        if len(matches) >= 1:
            last = matches[-1]
            page_html = page_html[:last.start()] + secondary_url + page_html[last.end():]
    return page_html


def build_page_in_background(job_id, lead):
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            page_future = executor.submit(_generate_page_html, lead)
            image_future = executor.submit(generate_images_for_page, lead)

            page_html = page_future.result(timeout=80)
            try:
                images = image_future.result(timeout=80)
            except Exception as img_err:
                print(f"[build] Image generation failed, continuing without: {img_err}")
                images = {}

        page_html = _inject_images_into_page(page_html, images)

        if page_html:
            with build_lock:
                build_jobs[job_id]["status"] = "done"
                build_jobs[job_id]["page"] = page_html
            save_lead_to_db(job_id, lead, status="done", page_html=page_html)
        else:
            print(f"[build] Invalid HTML generated for job {job_id}")
            with build_lock:
                build_jobs[job_id]["status"] = "error"
                build_jobs[job_id]["page"] = None
            save_lead_to_db(job_id, lead, status="error")

    except Exception as e:
        print(f"[build] Error building page for job {job_id}: {e}")
        with build_lock:
            build_jobs[job_id]["status"] = "error"
            build_jobs[job_id]["page"] = None
        save_lead_to_db(job_id, lead, status="error")


def build_context_block(context):
    if not context:
        return ""
    parts = ["VISITOR CONTEXT (use this to personalize your greeting — stay professional, no emojis):"]
    entry = context.get("entryPoint", "")
    if entry == "work_with_me":
        parts.append("- They clicked 'Work with me' — they may want info first.")
    elif entry == "cta":
        parts.append("- They clicked 'Ready to build yours' — they're ready to start.")
    elif entry.startswith("demo_"):
        demo_name = entry.replace("demo_", "").replace("_", " ").title()
        parts.append(f"- They were viewing the {demo_name} industry demo. Mention it briefly.")
    style = context.get("activeStyle", "")
    if style:
        parts.append(f"- They were viewing the '{style}' design theme. You can reference it.")
    custom_prompt = context.get("customPrompt", "")
    if custom_prompt:
        parts.append(f"- They described their vision as: \"{custom_prompt}\". Acknowledge it.")
    device = context.get("device", "")
    if device == "mobile":
        parts.append("- They're on mobile. If they seem hesitant, mention WhatsApp (+31 6 18072754) as an option.")
    return "\n".join(parts)


def build_lead_summary(lead_context):
    if not lead_context:
        return ""
    collected = {k: v for k, v in lead_context.items() if v}
    if not collected:
        return ""
    lines = ["ALREADY COLLECTED (do NOT ask for these again):"]
    for k, v in collected.items():
        lines.append(f"- {k}: {v}")
    lines.append("Skip these fields and ask for the NEXT missing field in the conversation flow.")
    return "\n".join(lines)


def call_chat_model(api_messages, lead_context, visitor_context=None):
    context_block = build_context_block(visitor_context)
    lead_summary = build_lead_summary(lead_context)
    system_prompt = CHAT_SYSTEM_PROMPT.format(context_block=context_block, lead_summary=lead_summary)

    full_messages = [{"role": "system", "content": system_prompt}, *api_messages]

    response = xai_client.chat.completions.create(
        model=CHAT_MODEL,
        messages=full_messages,
        max_tokens=1024,
    )
    raw = response.choices[0].message.content or ""
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        print(f"[chat] AI returned non-JSON, wrapping as reply")
        result = {"reply": raw, "lead": lead_context or {}}

    lead_defaults = {
        "name": "", "email": "", "phone": "", "business": "", "type": "", "vibe": "",
        "tagline": "", "colors": "", "services": "", "audience": "", "features": "",
    }
    lead = result.get("lead", {})
    if not isinstance(lead, dict):
        lead = {}

    for k in lead_context:
        if lead_context.get(k) and not lead.get(k):
            lead[k] = lead_context[k]

    for k, v in lead_defaults.items():
        if k not in lead or not isinstance(lead.get(k), str):
            lead[k] = v

    VALID_VIBES = {"Warm & Elegant", "Dark & Bold", "Clean & Minimal", "Loud & Electric", "Playful & Fun", "Raw & Edgy", ""}
    if lead.get("vibe", "") not in VALID_VIBES:
        lead["vibe"] = ""

    return result, lead


@app.route("/")
def index():
    return send_from_directory(".", "index.html")


@app.route("/api/design", methods=["POST"])
def api_design():
    data = request.get_json(silent=True) or {}
    prompt = data.get("prompt", "").strip()
    if not prompt:
        return jsonify({"error": "Please describe a style."}), 400

    try:
        response = xai_client.chat.completions.create(
            model=DESIGN_MODEL,
            messages=[
                {"role": "system", "content": STYLE_SCHEMA_DESCRIPTION},
                {"role": "user", "content": prompt},
            ],
            max_tokens=1024,
        )
        raw = response.choices[0].message.content.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        style = json.loads(raw)

        REQUIRED_FIELDS = {
            "name": "Custom",
            "bg": "#0a0a0a",
            "fg": "#f0f0f0",
            "accent": "#888",
            "cardBg": "rgba(255,255,255,0.05)",
            "cardBorder": "1px solid rgba(255,255,255,0.1)",
            "cardBlur": False,
            "labelFont": "Fira Code",
            "headlineFont": "Syne",
            "headlineWeight": 700,
            "headlineSize": "clamp(1.8rem, 5vw, 3rem)",
            "bodyFont": "Familjen Grotesk",
            "bodyColor": "#888",
            "indicatorBg": "rgba(255,255,255,0.1)",
            "overlay": "none",
        }
        for field, default in REQUIRED_FIELDS.items():
            if field not in style:
                style[field] = default

        VALID_OVERLAYS = {"none", "scanlines", "grid", "memphis"}
        if style.get("overlay") not in VALID_OVERLAYS:
            style["overlay"] = "none"

        font_fields = ["labelFont", "headlineFont", "bodyFont"]
        for ff in font_fields:
            if style.get(ff) not in AVAILABLE_FONTS:
                style[ff] = "Familjen Grotesk"

        return jsonify(style)

    except json.JSONDecodeError:
        return jsonify({"error": "AI returned invalid JSON. Please try again."}), 500
    except Exception as e:
        error_msg = str(e)
        print(f"[design] Error: {error_msg}")
        return jsonify({"error": f"AI error: {error_msg}"}), 500


@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json(silent=True) or {}
    messages = data.get("messages", [])
    lead_context = data.get("lead", {})
    visitor_context = data.get("context", {})

    api_messages = []
    for msg in messages:
        role = "user" if msg.get("role") == "user" else "assistant"
        text = msg.get("text", "")
        if text:
            api_messages.append({"role": role, "content": text})

    empty_lead = {"name": "", "email": "", "phone": "", "business": "", "type": "", "vibe": "", "tagline": "", "colors": "", "services": "", "audience": "", "features": ""}

    if not api_messages:
        context_block = build_context_block(visitor_context)
        system_prompt = CHAT_SYSTEM_PROMPT.format(context_block=context_block, lead_summary="")
        try:
            response = xai_client.chat.completions.create(
                model=CHAT_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": "[The visitor just opened the chat. Greet them based on the context provided. Keep it short and engaging.]"},
                ],
                max_tokens=512,
            )
            raw = response.choices[0].message.content or ""
            raw = raw.strip()
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            result = json.loads(raw)
            greeting = result.get("reply", "Hey! Tell me about your business and I'll design something for you right now.")
        except Exception:
            greeting = "I'm Tobias Bouw's assistant. What's your business name?"
        return jsonify({
            "reply": greeting,
            "lead": empty_lead,
            "buildTriggered": False,
        })

    try:
        result, lead = call_chat_model(api_messages, lead_context, visitor_context)
    except Exception as e:
        error_msg = str(e)
        print(f"[chat] Error: {error_msg}")
        return jsonify({"error": "Something went wrong. Please try again."}), 500

    has_design_essentials = lead.get("business") and lead.get("type") and lead.get("vibe")
    has_email = bool(lead.get("email"))
    existing_job = data.get("jobId")  # Frontend passes this after build triggered

    entry_ctx_str = json.dumps(visitor_context) if visitor_context else ""

    # Phase 1: Design essentials collected (business + type + vibe) — start building
    if has_design_essentials and not existing_job:
        job_id = str(uuid.uuid4())
        with build_lock:
            build_jobs[job_id] = {
                "status": "building",
                "page": None,
                "lead": lead.copy(),
                "email_collected": has_email
            }
        save_lead_to_db(job_id, lead, status="building", entry_context=entry_ctx_str)

        # Start background build
        thread = threading.Thread(target=build_page_in_background, args=(job_id, lead))
        thread.daemon = True
        thread.start()

        return jsonify({
            "reply": result.get("reply", "Understood. Continue."),
            "lead": lead,
            "buildTriggered": True,
            "jobId": job_id,
            "showPreview": False  # NEW: Don't show preview yet
        })

    # Phase 2: Build already started, continue conversation
    elif existing_job and existing_job in build_jobs:
        # Update lead data in job
        with build_lock:
            build_jobs[existing_job]["lead"] = lead.copy()
            build_jobs[existing_job]["email_collected"] = has_email
            build_status = build_jobs[existing_job]["status"]
            has_page = build_jobs[existing_job]["page"] is not None

        # Update database with enriched lead data
        save_lead_to_db(existing_job, lead, status=build_status, entry_context=entry_ctx_str)

        # Check if BOTH conditions met for preview
        show_preview = has_email and build_status == "done" and has_page

        return jsonify({
            "reply": result.get("reply", "Got it."),
            "lead": lead,
            "buildTriggered": True,
            "jobId": existing_job,
            "showPreview": show_preview,  # NEW: Signal when ready
            "page": build_jobs[existing_job]["page"] if show_preview else None
        })

    # Phase 0: Still collecting minimum data
    return jsonify({
        "reply": result.get("reply", "What's your business name?"),
        "lead": lead,
        "buildTriggered": False,
        "showPreview": False
    })


@app.route("/api/chat/status/<job_id>", methods=["GET"])
def chat_status(job_id):
    with build_lock:
        job = build_jobs.get(job_id)
        if not job:
            return jsonify({"status": "not_found"}), 404
        status = job["status"]
        page = job.get("page")
        email_collected = job.get("email_collected", False)

    if status == "building":
        return jsonify({
            "status": "building",
            "emailCollected": email_collected
        })
    elif status == "done":
        return jsonify({
            "status": "done",
            "page": page,
            "emailCollected": email_collected
        })
    else:
        return jsonify({"status": "error"})


@app.route("/api/chat/continue", methods=["POST"])
def chat_continue():
    data = request.get_json(silent=True) or {}
    messages = data.get("messages", [])
    lead_context = data.get("lead", {})
    visitor_context = data.get("context", {})

    api_messages = []
    for msg in messages:
        role = "user" if msg.get("role") == "user" else "assistant"
        text = msg.get("text", "")
        if text:
            api_messages.append({"role": role, "content": text})

    if not api_messages:
        return jsonify({"reply": "Tell me more!", "lead": lead_context})

    try:
        result, lead = call_chat_model(api_messages, lead_context, visitor_context)
        return jsonify({
            "reply": result.get("reply", "Tell me more!"),
            "lead": lead,
        })

    except Exception as e:
        print(f"[chat/continue] Error: {e}")
        return jsonify({
            "reply": "That sounds great! Tell me more about what you'd want on the site.",
            "lead": lead_context,
        })


@app.route("/api/leads", methods=["GET"])
def api_leads():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT id, job_id, business, type, vibe, email, name, phone, tagline, colors, services, audience, features, status, entry_context, created_at FROM leads ORDER BY created_at DESC LIMIT 100")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        leads = []
        for row in rows:
            leads.append({
                "id": row[0],
                "job_id": row[1],
                "business": row[2],
                "type": row[3],
                "vibe": row[4],
                "email": row[5],
                "name": row[6],
                "phone": row[7],
                "tagline": row[8],
                "colors": row[9],
                "services": row[10],
                "audience": row[11],
                "features": row[12],
                "status": row[13],
                "entry_context": row[14],
                "created_at": row[15].isoformat() if row[15] else None,
            })
        return jsonify(leads)
    except Exception as e:
        print(f"[leads] Error: {e}")
        return jsonify({"error": "Failed to fetch leads"}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
