import os
import json
import re
import uuid
import threading
import urllib.request
from flask import Flask, request, jsonify, send_from_directory
from anthropic import Anthropic
from openai import OpenAI
import resend

app = Flask(__name__, static_folder=".", static_url_path="")

AI_INTEGRATIONS_ANTHROPIC_API_KEY = os.environ.get("AI_INTEGRATIONS_ANTHROPIC_API_KEY")
AI_INTEGRATIONS_ANTHROPIC_BASE_URL = os.environ.get("AI_INTEGRATIONS_ANTHROPIC_BASE_URL")

anthropic_client = Anthropic(
    api_key=AI_INTEGRATIONS_ANTHROPIC_API_KEY,
    base_url=AI_INTEGRATIONS_ANTHROPIC_BASE_URL,
)

AI_INTEGRATIONS_OPENROUTER_API_KEY = os.environ.get("AI_INTEGRATIONS_OPENROUTER_API_KEY")
AI_INTEGRATIONS_OPENROUTER_BASE_URL = os.environ.get("AI_INTEGRATIONS_OPENROUTER_BASE_URL")

openrouter_client = OpenAI(
    api_key=AI_INTEGRATIONS_OPENROUTER_API_KEY,
    base_url=AI_INTEGRATIONS_OPENROUTER_BASE_URL,
)

TOBIAS_EMAIL = os.environ.get("TOBIAS_EMAIL", "")

def get_resend_credentials():
    hostname = os.environ.get("REPLIT_CONNECTORS_HOSTNAME")
    token = os.environ.get("REPL_IDENTITY")
    if token:
        token = "repl " + token
    else:
        renewal = os.environ.get("WEB_REPL_RENEWAL")
        if renewal:
            token = "depl " + renewal
    if not token or not hostname:
        return None, None
    try:
        req = urllib.request.Request(
            f"https://{hostname}/api/v2/connection?include_secrets=true&connector_names=resend",
            headers={"Accept": "application/json", "X_REPLIT_TOKEN": token},
        )
        r = urllib.request.urlopen(req, timeout=5)
        data = json.loads(r.read())
        item = data.get("items", [None])[0] if data.get("items") else None
        if item and item.get("settings", {}).get("api_key"):
            return item["settings"]["api_key"], item["settings"].get("from_email", "")
    except Exception as e:
        print(f"[resend] Failed to get credentials: {e}")
    return None, None


def send_email(to_email, subject, html_body):
    api_key, from_email = get_resend_credentials()
    if not api_key or not from_email:
        print("[resend] No credentials available, skipping email")
        return False
    try:
        resend.api_key = api_key
        resend.Emails.send({
            "from": from_email,
            "to": [to_email],
            "subject": subject,
            "html": html_body,
        })
        print(f"[resend] Email sent to {to_email}")
        return True
    except Exception as e:
        print(f"[resend] Failed to send email: {e}")
        return False


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

        message = anthropic_client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=8192,
            messages=[{"role": "user", "content": prompt}],
        )
        page_html = message.content[0].text or ""

        page_html = re.sub(r"^```(?:html)?\s*", "", page_html.strip())
        page_html = re.sub(r"\s*```$", "", page_html)

        if "<!DOCTYPE" not in page_html.upper():
            page_html = None

        with build_lock:
            build_jobs[job_id]["status"] = "done"
            build_jobs[job_id]["page"] = page_html

        if page_html and lead.get("email"):
            send_lead_email(lead, page_html)
        if page_html and TOBIAS_EMAIL:
            send_tobias_notification(lead, page_html)

    except Exception as e:
        print(f"[build] Error building page for job {job_id}: {e}")
        with build_lock:
            build_jobs[job_id]["status"] = "error"
            build_jobs[job_id]["page"] = None


def send_lead_email(lead, page_html):
    biz = lead.get("business", "your business")
    name = lead.get("name", "")
    greeting = f"Hey {name}," if name else "Hey,"

    email_html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body {{ margin:0; padding:0; background:#0a0a0a; color:#f0f0f0; font-family:'Segoe UI',system-ui,sans-serif; }}
.container {{ max-width:600px; margin:0 auto; padding:40px 24px; }}
h1 {{ font-size:28px; font-weight:700; margin-bottom:8px; }}
.accent {{ color:#ff2975; }}
p {{ line-height:1.7; color:#999; font-size:15px; }}
.preview-box {{ margin:32px 0; padding:24px; border:1px solid rgba(255,255,255,0.1); border-radius:12px; background:rgba(255,255,255,0.03); }}
.preview-box h2 {{ font-size:18px; margin:0 0 8px; color:#f0f0f0; }}
.preview-box p {{ margin:0; font-size:14px; }}
.cta {{ display:inline-block; margin-top:24px; padding:14px 32px; background:#ff2975; color:#fff; text-decoration:none; border-radius:999px; font-weight:700; font-size:15px; }}
.footer {{ margin-top:48px; padding-top:24px; border-top:1px solid rgba(255,255,255,0.1); font-size:13px; color:#555; }}
</style></head><body>
<div class="container">
<h1>I built <span class="accent">{biz}</span>'s website.</h1>
<p>{greeting}</p>
<p>While we were chatting, I designed a website concept for <strong>{biz}</strong>. No catch — I just wanted to show you what's possible.</p>
<div class="preview-box">
<h2>Your custom website preview</h2>
<p>A personalized {lead.get('vibe', 'modern')} design built specifically for {biz}. Reply to this email to see the full interactive preview, or let's talk about making it real.</p>
</div>
<p>This is what I do — I build websites and automations for small businesses. One person, done in days, not months.</p>
<p>Interested? Just reply to this email.</p>
<p style="color:#f0f0f0; font-weight:600; margin-top:32px;">— Tobias Bouw</p>
<p style="font-size:13px; color:#666;">tobiasbouw.com</p>
<div class="footer">
<p>You received this because you chatted with me on tobiasbouw.com. No spam, just one cool thing I made for you.</p>
</div>
</div></body></html>"""

    send_email(
        lead["email"],
        f"I built {biz}'s website — take a look",
        email_html,
    )


def send_tobias_notification(lead, page_html):
    email_html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>
body {{ margin:0; padding:0; background:#0a0a0a; color:#f0f0f0; font-family:'Segoe UI',system-ui,sans-serif; }}
.container {{ max-width:600px; margin:0 auto; padding:40px 24px; }}
h1 {{ font-size:24px; margin-bottom:16px; }}
.field {{ margin:8px 0; }}
.label {{ color:#ff2975; font-weight:600; font-size:13px; text-transform:uppercase; letter-spacing:0.5px; }}
.value {{ color:#f0f0f0; font-size:15px; margin-top:2px; }}
hr {{ border:none; border-top:1px solid rgba(255,255,255,0.1); margin:24px 0; }}
</style></head><body>
<div class="container">
<h1>New Lead from Chat</h1>
<div class="field"><div class="label">Name</div><div class="value">{lead.get('name', 'Not provided')}</div></div>
<div class="field"><div class="label">Email</div><div class="value">{lead.get('email', 'Not provided')}</div></div>
<div class="field"><div class="label">Business</div><div class="value">{lead.get('business', 'Not provided')}</div></div>
<div class="field"><div class="label">Type</div><div class="value">{lead.get('type', 'Not provided')}</div></div>
<div class="field"><div class="label">Vibe</div><div class="value">{lead.get('vibe', 'Not provided')}</div></div>
<hr>
<div class="field"><div class="label">Tagline</div><div class="value">{lead.get('tagline', 'Not provided')}</div></div>
<div class="field"><div class="label">Preferred Colors</div><div class="value">{lead.get('colors', 'Not provided')}</div></div>
<div class="field"><div class="label">Services</div><div class="value">{lead.get('services', 'Not provided')}</div></div>
<div class="field"><div class="label">Target Audience</div><div class="value">{lead.get('audience', 'Not provided')}</div></div>
<div class="field"><div class="label">Desired Features</div><div class="value">{lead.get('features', 'Not provided')}</div></div>
<hr>
<p style="color:#666; font-size:13px;">Website preview was generated and sent to the lead. The full HTML page is attached below for your reference.</p>
</div></body></html>"""

    send_email(
        TOBIAS_EMAIL,
        f"New Lead: {lead.get('business', 'Unknown')} — {lead.get('name', 'No name')}",
        email_html,
    )


CHAT_MODEL = "meta-llama/llama-3.3-70b-instruct"


def call_chat_model(api_messages, lead_context):
    response = openrouter_client.chat.completions.create(
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
        message = anthropic_client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=1024,
            system=STYLE_SCHEMA_DESCRIPTION,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()
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
        if "FREE_CLOUD_BUDGET_EXCEEDED" in error_msg:
            return jsonify({"error": "Cloud budget exceeded. Please try again later."}), 503
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
        if "FREE_CLOUD_BUDGET_EXCEEDED" in error_msg:
            return jsonify({"error": "Cloud budget exceeded."}), 503
        print(f"[chat] Error: {error_msg}")
        return jsonify({"error": "Something went wrong. Please try again."}), 500

    has_minimum = lead.get("business") and lead.get("type") and lead.get("vibe")
    has_email = bool(lead.get("email"))

    if has_minimum and has_email:
        job_id = str(uuid.uuid4())
        with build_lock:
            build_jobs[job_id] = {"status": "building", "page": None, "lead": lead.copy()}
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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
