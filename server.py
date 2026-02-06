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


CHAT_SYSTEM_PROMPT = """You are Tobias Bouw's AI assistant on his portfolio website (tobiasbouw.com). You help potential clients explore what a website could look like for their business. You're friendly, casual, professional, and genuinely enthusiastic about web design.

Your job: have a natural, engaging conversation to learn about the visitor's business. You're gathering info so Tobias can build them something amazing — but the visitor doesn't know that behind the scenes, a personalized website concept is being built for them while they chat. Keep it casual.

CONVERSATION FLOW:
1. Start by asking about their business (name, what they do)
2. Ask about their style/vibe preferences
3. Ask for their email so you can "send them something cool" or "keep them updated"
4. Keep gathering details — colors, tagline, key services, target audience, specific features they'd want
5. Be natural and reactive — comment on their answers, make design suggestions, show enthusiasm

INFORMATION TO GATHER (progressively, not as a checklist):
Required (get these first):
- business: Their business name
- type: What kind of business (Restaurant, Nightclub / Bar, Online Store, or Other)
- vibe: Style preference (Warm & Elegant, Dark & Bold, Clean & Minimal, Loud & Electric, Playful & Fun, Raw & Edgy)
- email: Their email address

Nice to have (ask while the site builds):
- name: Their name
- tagline: A slogan or tagline for their business
- colors: Any preferred colors
- services: Key services or products they offer
- audience: Who their target customers are
- features: Specific website features they want (booking, gallery, menu, shop, etc.)

IMPORTANT RULES:
- NEVER mention you're building a website in the background
- When they give their email, say something like "Perfect, I'll send you something cool." or "Check your inbox in a moment — I've got something for you."
- Keep the energy up — be excited about their business
- Ask ONE thing at a time, don't overwhelm them
- After getting email, keep asking about details (colors, services, etc.) — this buys time for the build

Your response must ALWAYS be valid JSON with this structure:
{
  "reply": "Your conversational message to the user",
  "lead": {
    "name": "their name or empty string",
    "email": "their email or empty string",
    "business": "business name or empty string",
    "type": "Restaurant|Nightclub / Bar|Online Store|Other or empty string",
    "vibe": "Warm & Elegant|Dark & Bold|Clean & Minimal|Loud & Electric|Playful & Fun|Raw & Edgy or empty string",
    "tagline": "their tagline or empty string",
    "colors": "preferred colors or empty string",
    "services": "key services/products or empty string",
    "audience": "target audience or empty string",
    "features": "desired features or empty string"
  }
}

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


def save_lead_to_db(job_id, lead, status="building", page_html=None):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO leads (job_id, business, type, vibe, email, name, tagline, colors, services, audience, features, page_html, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (job_id) DO UPDATE SET
                business = EXCLUDED.business,
                type = EXCLUDED.type,
                vibe = EXCLUDED.vibe,
                email = EXCLUDED.email,
                name = EXCLUDED.name,
                tagline = EXCLUDED.tagline,
                colors = EXCLUDED.colors,
                services = EXCLUDED.services,
                audience = EXCLUDED.audience,
                features = EXCLUDED.features,
                page_html = EXCLUDED.page_html,
                status = EXCLUDED.status,
                updated_at = CURRENT_TIMESTAMP
        """, (
            job_id,
            lead.get("business", ""),
            lead.get("type", ""),
            lead.get("vibe", ""),
            lead.get("email", ""),
            lead.get("name", ""),
            lead.get("tagline", ""),
            lead.get("colors", ""),
            lead.get("services", ""),
            lead.get("audience", ""),
            lead.get("features", ""),
            page_html,
            status,
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


def call_chat_model(api_messages, lead_context):
    response = xai_client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {"role": "system", "content": CHAT_SYSTEM_PROMPT},
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
        "name": "", "email": "", "business": "", "type": "", "vibe": "",
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

    api_messages = []
    for msg in messages:
        role = "user" if msg.get("role") == "user" else "assistant"
        text = msg.get("text", "")
        if text:
            api_messages.append({"role": role, "content": text})

    if not api_messages:
        return jsonify({
            "reply": "Hey! I'm Tobias's AI assistant. I build websites for small businesses — tell me about yours and let's see what I can do for you. What's your business called?",
            "lead": {"name": "", "email": "", "business": "", "type": "", "vibe": "", "tagline": "", "colors": "", "services": "", "audience": "", "features": ""},
            "buildTriggered": False,
        })

    try:
        result, lead = call_chat_model(api_messages, lead_context)
    except json.JSONDecodeError:
        return jsonify({
            "reply": "I'd love to hear more — tell me about your business!",
            "lead": lead_context or {"name": "", "email": "", "business": "", "type": "", "vibe": "", "tagline": "", "colors": "", "services": "", "audience": "", "features": ""},
            "buildTriggered": False,
        })
    except Exception as e:
        error_msg = str(e)
        print(f"[chat] Error: {error_msg}")
        return jsonify({"error": "Something went wrong. Please try again."}), 500

    has_minimum = lead.get("business") and lead.get("type") and lead.get("vibe")
    has_email = bool(lead.get("email"))

    if has_minimum and has_email:
        job_id = str(uuid.uuid4())
        with build_lock:
            build_jobs[job_id] = {"status": "building", "page": None, "lead": lead.copy()}
        save_lead_to_db(job_id, lead, status="building")
        thread = threading.Thread(target=build_page_in_background, args=(job_id, lead))
        thread.daemon = True
        thread.start()

        return jsonify({
            "reply": result.get("reply", "Perfect! Let me put something together for you..."),
            "lead": lead,
            "buildTriggered": True,
            "jobId": job_id,
        })

    return jsonify({
        "reply": result.get("reply", "Tell me more about your business!"),
        "lead": lead,
        "buildTriggered": False,
    })


@app.route("/api/chat/status/<job_id>", methods=["GET"])
def chat_status(job_id):
    with build_lock:
        job = build_jobs.get(job_id)
        if not job:
            return jsonify({"status": "not_found"}), 404
        status = job["status"]
        page = job.get("page")

    if status == "building":
        return jsonify({"status": "building"})
    elif status == "done":
        return jsonify({"status": "done", "page": page})
    else:
        return jsonify({"status": "error"})


@app.route("/api/chat/continue", methods=["POST"])
def chat_continue():
    data = request.get_json(silent=True) or {}
    messages = data.get("messages", [])
    lead_context = data.get("lead", {})

    api_messages = []
    for msg in messages:
        role = "user" if msg.get("role") == "user" else "assistant"
        text = msg.get("text", "")
        if text:
            api_messages.append({"role": role, "content": text})

    if not api_messages:
        return jsonify({"reply": "Tell me more!", "lead": lead_context})

    try:
        result, lead = call_chat_model(api_messages, lead_context)
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
        cur.execute("SELECT id, job_id, business, type, vibe, email, name, tagline, colors, services, audience, features, status, created_at FROM leads ORDER BY created_at DESC LIMIT 100")
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
                "tagline": row[7],
                "colors": row[8],
                "services": row[9],
                "audience": row[10],
                "features": row[11],
                "status": row[12],
                "created_at": row[13].isoformat() if row[13] else None,
            })
        return jsonify(leads)
    except Exception as e:
        print(f"[leads] Error: {e}")
        return jsonify({"error": "Failed to fetch leads"}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
