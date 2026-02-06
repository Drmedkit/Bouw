import os
import json
import re
import uuid
import threading
import pg8000
from urllib.parse import urlparse
from flask import Flask, request, jsonify, send_from_directory
from openai import OpenAI

app = Flask(__name__, static_folder=".", static_url_path="")

# xAI Grok client (OpenAI-compatible)
xai_client = OpenAI(
    api_key=os.environ.get("XAI_API_KEY"),
    base_url="https://api.x.ai/v1",
)

CHAT_MODEL = "grok-4-1-fast-non-reasoning"
BUILD_MODEL = "grok-4-1-fast"
DESIGN_MODEL = "grok-4-1-fast-non-reasoning"

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db():
    parsed = urlparse(DATABASE_URL)
    conn = pg8000.connect(
        host=parsed.hostname,
        port=parsed.port or 5432,
        user=parsed.username,
        password=parsed.password,
        database=parsed.path.lstrip("/"),
        ssl_context=True,
    )
    conn.autocommit = True
    return conn

build_jobs = {}
build_lock = threading.Lock()

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

PHASE 1 — Core requirements (ask these FIRST):
1. business: Their business name ("What's your business called?")
2. type: Business category (Restaurant, Nightclub / Bar, Online Store, or Other)
   - Ask: "What type of business is it? Restaurant, bar, online store, or something else?"
3. vibe: Design preference (Warm & Elegant, Dark & Bold, Clean & Minimal, Loud & Electric, Playful & Fun, Raw & Edgy)
   - Ask: "Which style direction fits? Warm & elegant, dark & bold, clean & minimal, loud & electric, playful & fun, or raw & edgy?"
   - If they're unsure: "Dark & bold works well for bars. Clean & minimal suits professional services."

IMPORTANT: Once you have business + type + vibe, continue gathering details. Don't mention anything is being built.

PHASE 2 — Email (REQUIRED):
4. email: Their email address ("What's your email?")
   - After receiving: Continue gathering additional details below

PHASE 3 — Additional details (gather these after email):
5. name: Their name ("What's your name?")
6. tagline: Business tagline ("Do you have a tagline or slogan?")
7. colors: Brand colors ("Any specific brand colors?")
8. services: Key offerings ("What are your main products or services?")
9. audience: Target market ("Who's your target audience?")
10. phone: Contact number ("Best number to reach you?")
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
- Don't mention background processes

{context_block}

Your response must ALWAYS be valid JSON with this structure:
{{
  "reply": "Your professional message to the user",
  "lead": {{
    "name": "their name or empty string",
    "email": "their email or empty string",
    "phone": "their phone number or empty string",
    "business": "business name or empty string",
    "type": "Restaurant|Nightclub / Bar|Online Store|Other or empty string",
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
- Has a stunning hero section with a relevant Unsplash background image (use ?w=1200&h=800&fit=crop)
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
    except Exception as e:
        print(f"[db] Error saving lead: {e}")


def build_page_in_background(job_id, lead):
    try:
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
        page_html = response.choices[0].message.content or ""

        page_html = re.sub(r"^```(?:html)?\s*", "", page_html.strip())
        page_html = re.sub(r"\s*```$", "", page_html)

        if "<!DOCTYPE" not in page_html.upper():
            page_html = None

        with build_lock:
            build_jobs[job_id]["status"] = "done"
            build_jobs[job_id]["page"] = page_html

        save_lead_to_db(job_id, lead, status="done", page_html=page_html)

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


def call_chat_model(api_messages, lead_context, visitor_context=None):
    context_block = build_context_block(visitor_context)
    system_prompt = CHAT_SYSTEM_PROMPT.format(context_block=context_block)

    response = xai_client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            *api_messages,
        ],
        max_tokens=1024,
    )
    raw = response.choices[0].message.content or ""
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    result = json.loads(raw)

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

    VALID_TYPES = {"Restaurant", "Nightclub / Bar", "Online Store", "Other", ""}
    if lead.get("type", "") not in VALID_TYPES:
        lead["type"] = "Other"

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
        system_prompt = CHAT_SYSTEM_PROMPT.format(context_block=context_block)
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
    except json.JSONDecodeError:
        return jsonify({
            "reply": "What's your business name?",
            "lead": lead_context or empty_lead,
            "buildTriggered": False,
        })
    except Exception as e:
        error_msg = str(e)
        print(f"[chat] Error: {error_msg}")
        return jsonify({"error": "Something went wrong. Please try again."}), 500

    has_minimum = lead.get("business") and lead.get("type") and lead.get("vibe")
    has_email = bool(lead.get("email"))
    existing_job = data.get("jobId")  # Frontend passes this after build triggered

    entry_ctx_str = json.dumps(visitor_context) if visitor_context else ""

    # Phase 1: Minimum data collected, trigger build immediately
    if has_minimum and not existing_job:
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
