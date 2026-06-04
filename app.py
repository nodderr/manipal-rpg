import os
import json
import re
import random
from flask import Flask, render_template, request, jsonify, session
# Removed flask_session for client-side cookies compatibility in serverless environments
import google.generativeai as genai
from dotenv import load_dotenv
from engine import GameState

load_dotenv()

app = Flask(__name__)
app.secret_key = "SUPER_SECRET_KEY"

# Using standard client-side signed cookies for sessions to support Vercel serverless deployment
app.config["SESSION_PERMANENT"] = True

# --- GEMINI CONFIGURATION ---
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# --- DATA LOADING ---
ALL_ITEMS = []
try:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    LORE_PATH = os.path.join(BASE_DIR, 'manipal_lore.txt')
    with open(LORE_PATH, 'r', encoding='utf-8') as f:
        CAMPUS_DATA = f.read()
    if "[ITEMS & LOOT]" in CAMPUS_DATA:
        item_section = CAMPUS_DATA.split("[ITEMS & LOOT]")[1].split("[EVENTS]")[0]
        for line in item_section.split('\n'):
            line = line.strip()
            if line and (line[0].isdigit() or line.startswith("-")):
                clean_item = re.sub(r'^\d+\.\s*', '', line)
                ALL_ITEMS.append(clean_item)
except FileNotFoundError:
    CAMPUS_DATA = "Location: A generic university campus."
    ALL_ITEMS = ["Potion [+10 HP]"]

FRIEND_ZONES_LIST = [
    "D406 (Noddy's Room) - Chaotic roommate energy",
    "E106 (Aryan's Room) - Balanced zone",
    "A409 (Tushar's Room) - Strategic discussion hub",
    "Ideal Residency (Shaivi's Home) - Calm residential zone",
    "Mandavi Paradise (Mathur's Home) - Peaceful but isolated",
    "Woodwinds (Shivansh's Home) - Premium apartment buffs",
    "E503 (Mihika's Room) - High aesthetic value",
    "B601 (Ramya's Room) - Cooperative living bonuses",
    "C904 (Reva, Anshu, Disha, Adel's Room) - Cozy group zone",
    "Babas Point - Scenic, quiet place",
    "Petrol Pump - Late-night tea zone"
]

RUNES_LIST = [
    "Rune of the CEO [+2500 Gold]",
    "Rune of Vitality [+300 HP]",
    "Rune of Destruction [+150 ATK]",
    "Rune of the Topper [+80 ATK] [+80 HP]",
    "Rune of Greed [+5000 Gold] [-50 HP]",
    "Rune of Immortality [+500 HP] [-50 ATK]",
    "Rune of Chaos [+200 ATK] [-100 HP]",
    "Rune of Speed [+50 HP] [+50 ATK] [+1000 Gold]",
    "Rune of Manipal [+100 HP] [+100 ATK] [+1500 Gold]"
]

SYSTEM_PROMPT = f"""
You are the Dungeon Master for a **Surreal Fantasy RPG** set in **Manipal (MAHE Campus)**.
THEME: Mix D&D with modern Campus Life.

WORLD DATA:
{CAMPUS_DATA}

RULES:
1. Game ends Turn 50.
2. Every 10th Turn is a BOSS FIGHT.
3. Provide exactly 4 distinct options.

*** CRITICAL STAT RULES ***
1. **OPTIONS MUST HAVE TAGS**: You MUST include tags in square brackets for any stat change.
   - CORRECT: "Eat Puff [+20 HP] [-20 Gold]"
   - WRONG: "Eat Puff"
2. **STORY VISUALS**: If the user gains/loses anything in the story, append the tag.
   - Example: "You find a coin. [+100 Gold]"

OUTPUT FORMAT (JSON ONLY):
{{
    "story": "Description...",
    "options": ["Opt 1 [+X HP]", "Opt 2", "Opt 3", "Opt 4"]
}}
"""

# --- BUG 3 FIX: Max messages kept in session to prevent cookie overflow ---
# Flask cookie limit is 4KB. The system prompt alone is ~4KB, so we never
# store it in the session. We only keep the last N conversation turns as a
# sliding window, and inject the system prompt fresh each request.
MAX_HISTORY_MESSAGES = 6  # 3 user + 3 assistant turns


def clean_json(text):
    text = text.strip()
    if text.startswith("```json"): text = text[7:]
    if text.startswith("```"): text = text[3:]
    if text.endswith("```"): text = text[:-3]
    return text

def parse_tags(text):
    """
    Parses stat tags from text.
    Handles: [+50 Gold], [-20 HP], [+10 ATK], etc.
    Used for: reading affordability from button text, applying stats from AI story.
    """
    changes = {"hp": 0, "gold": 0, "attack": 0}
    matches = re.findall(r'\[\s*([+\-]?\s*\d+)\s*(HP|Gold|ATK|Attack)\s*\]', text, re.IGNORECASE)
    for val_str, type_ in matches:
        try:
            val = int(val_str.replace(" ", ""))
            type_ = type_.lower()
            if 'hp' in type_: changes['hp'] += val
            elif 'gold' in type_: changes['gold'] += val
            elif 'atk' in type_ or 'attack' in type_: changes['attack'] += val
        except ValueError:
            continue
    return changes

def get_random_items(count=3):
    if not ALL_ITEMS: return ""
    selected = random.sample(ALL_ITEMS, min(len(ALL_ITEMS), count))
    return ", ".join(selected)

def load_game_from_session(data):
    """Reconstruct a GameState object from session data."""
    game = GameState()
    game.turn = data['turn']
    game.hp = data['hp']
    game.max_hp = data.get('max_hp', 100)
    game.gold = data['gold']
    game.attack = data.get('attack', 10)
    game.runes = data.get('runes', [])
    return game


@app.route('/')
def home():
    new_game = GameState()
    new_game.gold = 500
    session['current_options'] = ["Start Adventure", "Check Inventory", "Rest", "Explore"]
    session['awaiting_rune'] = False
    # BUG 3 FIX: history is stored separately, NOT inside game_state dict
    session['short_history'] = []
    session['game_state'] = new_game.to_dict()
    return render_template('index.html', stats=new_game.to_dict())

@app.route('/action', methods=['POST'])
def action():
    data = session.get('game_state')
    if not data: return jsonify({"error": "No game found"}), 400

    game = load_game_from_session(data)

    user_choice = request.json.get('choice')

    # BUG 1 FIX: We only read button tags for the AFFORDABILITY CHECK.
    # We do NOT apply them to stats. The AI story is the authoritative source
    # of what actually happened, and its tags will be applied after the AI responds.
    button_stats = parse_tags(user_choice)

    # --- RUNE SELECTION LOGIC ---
    if session.get('awaiting_rune'):
        game.runes.append(user_choice)
        # Rune stats come directly from the rune text — apply them once.
        game.update_stats(button_stats)
        # BUG 2 FIX: Increment turn exactly once, explicitly.
        game.turn += 1
        session['awaiting_rune'] = False

        bridge_story = f"You absorb the power of the {user_choice}! You feel invincible."
        next_options = ["Continue Adventure", "Check Stats", "Roar", "Look for Enemies"]

        session['current_options'] = next_options
        session['game_state'] = game.to_dict()
        return jsonify({
            "message": bridge_story,
            "stats": game.to_dict(),
            "options": next_options
        })

    # --- CHECK GOLD AFFORDABILITY (read-only from button tags) ---
    gold_cost = button_stats.get('gold', 0)
    if gold_cost < 0 and (game.gold + gold_cost < 0):
        old_options = session.get('current_options', [])
        return jsonify({
            "message": f"🚫 You check your wallet... only {game.gold} Gold. You need {abs(gold_cost)} Gold!",
            "stats": game.to_dict(),
            "options": old_options
        })

    # --- RUNE TRIGGER (Every 10 Turns) ---
    if game.turn % 10 == 9:
        rune_options = random.sample(RUNES_LIST, 2)
        session['awaiting_rune'] = True
        special_message = f"✨ LEVEL {game.turn} REACHED! ✨\nAncient Manipal Runes appear before you. Choose wisely."
        session['current_options'] = rune_options
        session['game_state'] = game.to_dict()
        return jsonify({
            "message": special_message,
            "stats": game.to_dict(),
            "options": rune_options
        })

    # --- STANDARD AI TURN ---
    suggested_loot = get_random_items(3)

    if random.random() < 0.40:
        forced_loc = random.choice(FRIEND_ZONES_LIST)
        special_instruction = f"NARRATIVE OVERRIDE: The player has stumbled into {forced_loc}."
    else:
        special_instruction = ""

    turn_context = f"""
    Current Turn: {game.turn}
    HP: {game.hp}/{game.max_hp}
    Gold: {game.gold}
    Attack: {game.attack}
    Choice: {user_choice}
    SUGGESTED LOOT: {suggested_loot}
    {special_instruction}
    """

    # BUG 3 FIX: Retrieve the sliding window of recent messages from the session.
    # The system prompt is always injected fresh — never from the session.
    short_history = session.get('short_history', [])

    try:
        # Build Gemini history from the sliding window (already in Gemini role format)
        gemini_history = short_history  # list of {"role": "user"/"model", "parts": [...]}

        # Initialize Model with System Prompt (fresh, not from session)
        model = genai.GenerativeModel(
            model_name="gemini-3-flash-preview",
            system_instruction=SYSTEM_PROMPT
        )

        # Start Chat Session with recent history context
        chat = model.start_chat(history=gemini_history)

        # Send Message
        response = chat.send_message(
            turn_context,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json"
            )
        )

        response_text = response.text
        clean_text = clean_json(response_text)
        ai_data = json.loads(clean_text)

        # BUG 1 FIX: Apply stats ONLY from the AI story — never from button text.
        # The story is the single source of truth for what actually happened.
        story_stats = parse_tags(ai_data["story"])
        game.update_stats(story_stats)

        # BUG 2 FIX: Increment turn exactly once per successful player action.
        game.turn += 1

        # Check for game over after turn increment
        if game.turn > game.max_turns:
            game.is_game_over = True

        # BUG 3 FIX: Update the sliding window. Append the new user + model exchange,
        # then trim to keep only the last MAX_HISTORY_MESSAGES messages.
        short_history.append({"role": "user", "parts": [turn_context]})
        short_history.append({"role": "model", "parts": [response_text]})
        if len(short_history) > MAX_HISTORY_MESSAGES:
            short_history = short_history[-MAX_HISTORY_MESSAGES:]

        session['short_history'] = short_history
        session['current_options'] = ai_data["options"]
        session['game_state'] = game.to_dict()

        return jsonify({
            "message": ai_data["story"],
            "stats": game.to_dict(),
            "options": ai_data["options"]
        })

    except Exception as e:
        print(f"AI Error: {e}")
        return jsonify({
            "message": "Connection Error (Gemini).",
            "stats": game.to_dict(),
            "options": session.get('current_options', [])
        })

if __name__ == '__main__':
    app.run(debug=True)