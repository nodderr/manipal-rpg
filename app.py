import os
import json
import re
import random
from flask import Flask, render_template, request, jsonify, session
from flask_session import Session
from groq import Groq
from dotenv import load_dotenv
from engine import GameState

load_dotenv()

app = Flask(__name__)
app.secret_key = "SUPER_SECRET_KEY"

app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# --- DATA LOADING ---
ALL_ITEMS = []
try:
    with open('manipal_lore.txt', 'r', encoding='utf-8') as f:
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

def clean_json(text):
    text = text.strip()
    if text.startswith("```json"): text = text[7:]
    if text.startswith("```"): text = text[3:]
    if text.endswith("```"): text = text[:-3]
    return text

def parse_tags(text):
    """
    Robust parsing for stats.
    Handles: [+50 Gold], [Gold +50], [ + 50 Gold ], etc.
    """
    changes = {"hp": 0, "gold": 0, "attack": 0}
    
    # improved regex to be more flexible with spacing and order
    # Looks for [ ... number ... type ... ]
    matches = re.findall(r'\[\s*([+\-]?\s*\d+)\s*(HP|Gold|ATK|Attack)\s*\]', text, re.IGNORECASE)
    
    for val_str, type_ in matches:
        try:
            val = int(val_str.replace(" ", "")) # Remove spaces inside number "+ 50" -> 50
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


@app.route('/')
def home():
    new_game = GameState()
    new_game.gold = 500 
    new_game.history = [{"role": "system", "content": SYSTEM_PROMPT}]
    session['current_options'] = ["Start Adventure", "Check Inventory", "Rest", "Explore"]
    session['awaiting_rune'] = False
    session['game_state'] = new_game.to_dict()
    return render_template('index.html', stats=new_game.to_dict())

@app.route('/action', methods=['POST'])
def action():
    data = session.get('game_state')
    if not data: return jsonify({"error": "No game found"}), 400
    
    game = GameState()
    game.turn = data['turn']
    game.hp = data['hp']
    
    # --- FIX FOR MAX HP RESETTING ---
    # We must load max_hp from the session, otherwise it defaults to 100 every time.
    game.max_hp = data.get('max_hp', 100) 
    
    game.gold = data['gold']
    game.attack = data.get('attack', 10)
    game.runes = data.get('runes', [])
    game.history = data.get('history', [])

    user_choice = request.json.get('choice')
    button_stats = parse_tags(user_choice)

    # --- RUNE SELECTION LOGIC ---
    if session.get('awaiting_rune'):
        game.runes.append(user_choice) 
        game.update_stats(button_stats) 
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

    # Apply Button Stats (e.g. [-50 Gold] from buying something)
    game.update_stats(button_stats)
    
    # --- RUNE TRIGGER (Every 10 Turns) ---
    if game.turn % 10 == 0:
        rune_options = random.sample(RUNES_LIST, 3)
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
    
    game.history.append({"role": "user", "content": turn_context})

    try:
        chat_completion = client.chat.completions.create(
            messages=game.history,
            model="llama-3.1-8b-instant",
            temperature=1.0, 
            response_format={"type": "json_object"} 
        )
        
        response_text = chat_completion.choices[0].message.content
        clean_text = clean_json(response_text)
        ai_data = json.loads(clean_text)
        
        # Parse stats from the STORY text (e.g. "You found gold! [+500 Gold]")
        story_stats = parse_tags(ai_data["story"])
        game.update_stats(story_stats)

        session['current_options'] = ai_data["options"]

        game.history.append({"role": "assistant", "content": response_text})
        session['game_state'] = game.to_dict()
        
        return jsonify({
            "message": ai_data["story"],
            "stats": game.to_dict(),
            "options": ai_data["options"]
        })

    except Exception as e:
        print(f"AI Error: {e}")
        return jsonify({
            "message": "Connection Error.", 
            "stats": game.to_dict(),
            "options": session.get('current_options', [])
        })

if __name__ == '__main__':
    app.run(debug=True)