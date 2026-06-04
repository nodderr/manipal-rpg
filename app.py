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

# --- FRIEND ZONES (for narrative overrides) ---
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

# --- LOCATION STATS LOOKUP TABLE ---
# This is the SINGLE SOURCE OF TRUTH for all location/friend-zone stat rewards.
# The AI never touches these values. When a narrative override fires, the server
# applies these stats directly before the AI even writes its response.
LOCATION_STATS = {
    # Regular campus locations
    "Tiger Circle":         {"hp": 0,  "gold": 250,  "attack": 0},
    "Student Plaza":        {"hp": 0,  "gold": 300,  "attack": 0},
    "End Point":            {"hp": 0,  "gold": 400,  "attack": 0},
    "Venugopal Temple":     {"hp": 0,  "gold": 200,  "attack": 0},
    "Innovation Centre":    {"hp": 0,  "gold": 1000, "attack": 0},
    "Malpe Beach":          {"hp": 0,  "gold": 500,  "attack": 0},
    "Coin Circle":          {"hp": 0,  "gold": 150,  "attack": 0},
    # Friend zones — high-value rewards for visiting
    "D406":                 {"hp": 50, "gold": 800,  "attack": 20},
    "E106":                 {"hp": 50, "gold": 800,  "attack": 20},
    "A409":                 {"hp": 50, "gold": 800,  "attack": 20},
    "Ideal Residency":      {"hp": 50, "gold": 800,  "attack": 20},
    "Mandavi Paradise":     {"hp": 50, "gold": 800,  "attack": 20},
    "Woodwinds":            {"hp": 50, "gold": 800,  "attack": 20},
    "E503":                 {"hp": 50, "gold": 800,  "attack": 20},
    "B601":                 {"hp": 50, "gold": 800,  "attack": 20},
    "C904":                 {"hp": 50, "gold": 800,  "attack": 20},
    "Babas Point":          {"hp": 20, "gold": 0,    "attack": 0},
    "Petrol Pump":          {"hp": 20, "gold": 0,    "attack": 0},
}

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
2. **STORY VISUALS**: You may include stat tags in the story text as flavour (e.g. "You find a coin. [+250 Gold]"),
   but these are DISPLAY ONLY. The server manages all actual stat changes.

OUTPUT FORMAT (JSON ONLY):
{{
    "story": "Description...",
    "options": ["Opt 1 [+X HP]", "Opt 2", "Opt 3", "Opt 4"]
}}
"""

# BUG 3 FIX: Max messages kept in session to prevent cookie overflow.
# Flask cookie limit is 4KB. System prompt alone is ~4KB, so we never
# store it in the session. Only the last N turns as a sliding window.
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
    Used for: reading button tags (player choices) and rune tags.
    Story tags are NEVER parsed for stat application.
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

def get_location_stats(location_name):
    """
    Given a FRIEND_ZONES_LIST entry like "D406 (Noddy's Room) - Chaotic energy",
    fuzzy-matches against LOCATION_STATS keys and returns the stat dict.
    Returns a zero-stat dict if no match is found (safe default).
    """
    for key in LOCATION_STATS:
        if key.lower() in location_name.lower():
            return dict(LOCATION_STATS[key])  # return a copy
    return {"hp": 0, "gold": 0, "attack": 0}

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
    # BUG 3 FIX: history stored separately, NOT inside game_state dict
    session['short_history'] = []
    session['game_state'] = new_game.to_dict()
    return render_template('index.html', stats=new_game.to_dict())

@app.route('/action', methods=['POST'])
def action():
    data = session.get('game_state')
    if not data: return jsonify({"error": "No game found"}), 400

    game = load_game_from_session(data)
    user_choice = request.json.get('choice')

    # Parse button tags — used for affordability check AND stat application.
    # Button tags are the player's explicit choice contract.
    button_stats = parse_tags(user_choice)

    # --- RUNE SELECTION LOGIC ---
    if session.get('awaiting_rune'):
        game.runes.append(user_choice)
        # Rune stats come from rune text — apply once, server-controlled.
        game.update_stats(button_stats)
        game.turn += 1  # Increment turn exactly once
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

    # --- CHECK GOLD AFFORDABILITY ---
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

    # --- APPLY BUTTON STATS (player's chosen action) ---
    # This is applied BEFORE the AI call so the game state is authoritative.
    game.update_stats(button_stats)

    # --- NARRATIVE OVERRIDE: Server applies location stats directly ---
    # The AI is only told where the player is for narrative purposes.
    # The server looks up the location's stat reward and applies it here.
    location_bonus = {"hp": 0, "gold": 0, "attack": 0}
    special_instruction = ""

    if random.random() < 0.40:
        forced_loc = random.choice(FRIEND_ZONES_LIST)
        special_instruction = f"NARRATIVE OVERRIDE: The player has stumbled into {forced_loc}."
        location_bonus = get_location_stats(forced_loc)
        if any(v != 0 for v in location_bonus.values()):
            game.update_stats(location_bonus)

    # --- STANDARD AI TURN ---
    suggested_loot = get_random_items(3)

    # Build a human-readable location bonus string so AI can reference it in story
    bonus_desc = ""
    if any(v != 0 for v in location_bonus.values()):
        parts = []
        if location_bonus["gold"]: parts.append(f"+{location_bonus['gold']} Gold")
        if location_bonus["hp"]: parts.append(f"+{location_bonus['hp']} HP")
        if location_bonus["attack"]: parts.append(f"+{location_bonus['attack']} ATK")
        bonus_desc = f"LOCATION BONUS AWARDED BY SERVER: {', '.join(parts)} — weave this into the story naturally."

    turn_context = f"""
    Current Turn: {game.turn}
    HP: {game.hp}/{game.max_hp}
    Gold: {game.gold}
    Attack: {game.attack}
    Choice: {user_choice}
    SUGGESTED LOOT: {suggested_loot}
    {special_instruction}
    {bonus_desc}
    """

    # BUG 3 FIX: Use sliding window of recent messages — system prompt injected fresh each time.
    short_history = session.get('short_history', [])

    try:
        # Initialize Model with System Prompt (fresh each turn, not from session)
        model = genai.GenerativeModel(
            model_name="gemini-3-flash-preview",
            system_instruction=SYSTEM_PROMPT
        )

        # Start Chat Session with recent sliding-window history
        chat = model.start_chat(history=short_history)

        # Send current turn message
        response = chat.send_message(
            turn_context,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json"
            )
        )

        response_text = response.text
        clean_text = clean_json(response_text)
        ai_data = json.loads(clean_text)

        # BUG 1+2 FIX: Stats already applied above (button + location).
        # Story text is NEVER parsed for stats — it is narration only.
        # Increment turn exactly once after a successful AI response.
        game.turn += 1

        # Check for game over after turn increment
        if game.turn > game.max_turns:
            game.is_game_over = True

        # BUG 3 FIX: Update sliding window history (trim to last MAX_HISTORY_MESSAGES)
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