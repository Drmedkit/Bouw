import os
import json
import re
from flask import Flask, request, jsonify, send_from_directory
from anthropic import Anthropic

app = Flask(__name__, static_folder=".", static_url_path="")

AI_INTEGRATIONS_ANTHROPIC_API_KEY = os.environ.get("AI_INTEGRATIONS_ANTHROPIC_API_KEY")
AI_INTEGRATIONS_ANTHROPIC_BASE_URL = os.environ.get("AI_INTEGRATIONS_ANTHROPIC_BASE_URL")

client = Anthropic(
    api_key=AI_INTEGRATIONS_ANTHROPIC_API_KEY,
    base_url=AI_INTEGRATIONS_ANTHROPIC_BASE_URL,
)

AVAILABLE_FONTS = [
    "Syne", "Fira Code", "DM Serif Display", "Familjen Grotesk",
    "Instrument Serif", "Noto Serif JP", "Orbitron", "Unbounded",
    "Zilla Slab", "Courier Prime"
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


CHAT_SYSTEM_PROMPT = """You are Tobias Bouw's AI assistant on his portfolio website. You help potential clients explore what a website could look like for their business. You're friendly, professional, and enthusiastic about web design.

Your goal is to have a natural conversation to learn about the visitor's business, then generate a complete standalone HTML page as a preview of what their website could look like.

During the conversation, progressively gather this information:
- Their name
- Their email
- Their business name
- What type of business (restaurant, nightclub/bar, online store, or other)
- What vibe/style they want (warm & elegant, dark & bold, clean & minimal, loud & electric, playful & fun, raw & edgy)

Be conversational and natural — don't just ask questions in a list. React to their answers, make suggestions, show enthusiasm about their business.

When you have enough information (at minimum: business name, type, and some sense of vibe), generate a full standalone HTML page.

Your response must ALWAYS be valid JSON with this structure:
{
  "reply": "Your conversational message to the user",
  "lead": {
    "name": "their name or empty string",
    "email": "their email or empty string",
    "business": "business name or empty string",
    "type": "Restaurant|Nightclub / Bar|Online Store|Other or empty string",
    "vibe": "Warm & Elegant|Dark & Bold|Clean & Minimal|Loud & Electric|Playful & Fun|Raw & Edgy or empty string"
  },
  "page": null
}

When you're ready to show them a preview, set "page" to a COMPLETE standalone HTML page (<!DOCTYPE html> through </html>) that:
- Is fully self-contained with inline CSS
- Uses Google Fonts (load via CDN link)
- Has a hero section with a relevant Unsplash background image
- Has sections for their services/offerings
- Has a call-to-action section
- Is mobile-responsive
- Matches their requested vibe/style
- Uses their actual business name throughout
- Looks professional and polished

Pick Unsplash images that match their business type:
- Restaurant: https://images.unsplash.com/photo-1414235077428-338989a2e8c0?w=1200&h=800&fit=crop
- Nightclub: https://images.unsplash.com/photo-1514525253161-7a46d19cd819?w=1200&h=800&fit=crop
- E-commerce: https://images.unsplash.com/photo-1441984904996-e0b6ba687e04?w=1200&h=800&fit=crop
- Other/generic: https://images.unsplash.com/photo-1497366216548-37526070297c?w=1200&h=800&fit=crop

Only set "page" to a value when you have gathered enough info AND it feels natural in the conversation (don't generate a page on the very first message). Guide the conversation for at least 3-4 exchanges before generating.

Remember: respond with ONLY the JSON object. No markdown, no code fences, no explanation outside the JSON."""


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
        message = client.messages.create(
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

    api_messages = []
    for msg in messages:
        role = "user" if msg.get("role") == "user" else "assistant"
        text = msg.get("text", "")
        if text:
            api_messages.append({"role": role, "content": text})

    if not api_messages:
        return jsonify({
            "reply": "Hey! I'm Tobias's AI assistant. Tell me about your business and I'll design a website preview for you right now. What's your business called?",
            "lead": {"name": "", "email": "", "business": "", "type": "", "vibe": ""},
            "page": None,
        })

    try:
        message = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=8192,
            system=CHAT_SYSTEM_PROMPT,
            messages=api_messages,
        )
        raw = message.content[0].text.strip()

        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

        result = json.loads(raw)

        lead_defaults = {"name": "", "email": "", "business": "", "type": "", "vibe": ""}
        lead = result.get("lead", {})
        if not isinstance(lead, dict):
            lead = {}
        for k, v in lead_defaults.items():
            if k not in lead or not isinstance(lead[k], str):
                lead[k] = v

        VALID_TYPES = {"Restaurant", "Nightclub / Bar", "Online Store", "Other", ""}
        if lead.get("type", "") not in VALID_TYPES:
            lead["type"] = "Other"

        VALID_VIBES = {"Warm & Elegant", "Dark & Bold", "Clean & Minimal", "Loud & Electric", "Playful & Fun", "Raw & Edgy", ""}
        if lead.get("vibe", "") not in VALID_VIBES:
            lead["vibe"] = ""

        page = result.get("page")
        if page is not None and (not isinstance(page, str) or "<!DOCTYPE" not in page.upper()):
            page = None

        response = {
            "reply": result.get("reply", "Tell me more about your business!"),
            "lead": lead,
            "page": page,
        }
        return jsonify(response)

    except json.JSONDecodeError:
        return jsonify({
            "reply": "Let me try that again — tell me more about your business!",
            "lead": {"name": "", "email": "", "business": "", "type": "", "vibe": ""},
            "page": None,
        })
    except Exception as e:
        error_msg = str(e)
        if "FREE_CLOUD_BUDGET_EXCEEDED" in error_msg:
            return jsonify({"error": "Cloud budget exceeded."}), 503
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
