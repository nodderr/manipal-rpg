import os
import json
import re
import random
from flask import Flask, render_template, request, jsonify, session
from groq import Groq
from dotenv import load_dotenv
from engine import GameState

load_dotenv()

app = Flask(__name__)
app.secret_key = "SUPER_SECRET_KEY"

# Using standard client-side signed cookies for sessions to support Vercel serverless deployment
app.config["SESSION_PERMANENT"] = True

# --- GROQ CONFIGURATION ---
# Get your free API key at: https://console.groq.com
# Add GROQ_API_KEY to your .env file or Vercel environment variables.
GROQ_MODEL = "llama-3.3-70b-versatile"

# Groq — free, ultra-fast (~0.3s), uses Llama models
# Initialized lazily to prevent startup crash if GROQ_API_KEY is missing
_groq_client = None

def get_groq_client():
    global _groq_client
    if _groq_client is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY environment variable is not set on the server.")
        _groq_client = Groq(api_key=api_key)
    return _groq_client

# --- DATA LOADING ---
ALL_ITEMS = []
ALL_ENEMIES = []
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
    if "[ENEMIES & BOSSES]" in CAMPUS_DATA:
        enemy_section = CAMPUS_DATA.split("[ENEMIES & BOSSES]")[1].split("[ITEMS & LOOT]")[0]
        for line in enemy_section.split('\n'):
            line = line.strip()
            if line and (line[0].isdigit() or line.startswith("-")):
                clean_enemy = re.sub(r'^\d+\.\s*', '', line)
                name = clean_enemy.split(":")[0].strip()
                if "Anil Rana" not in name and "FINAL BOSS" not in name:
                    ALL_ENEMIES.append(name)
except FileNotFoundError:
    CAMPUS_DATA = "Location: A generic university campus."
    ALL_ITEMS = ["Potion [+10 HP]"]

if not ALL_ENEMIES:
    ALL_ENEMIES = [
        "The Auto Rickshaw Driver",
        "The Hostel Warden",
        "The Internal Assessment (IA)",
        "The Strict Invigilator",
        "The Stray Dog Pack",
        "The 8AM Lecture",
        "The Backlog",
        "The Assignment Deadline",
        "The Library Guard",
        "The Senior Student"
    ]

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
# Single source of truth for all location/friend-zone rewards.
# The AI never touches these — the server applies them directly.
LOCATION_STATS = {
    "Tiger Circle":         {"hp": 0,  "gold": 250,  "attack": 0},
    "Student Plaza":        {"hp": 0,  "gold": 300,  "attack": 0},
    "End Point":            {"hp": 0,  "gold": 400,  "attack": 0},
    "Venugopal Temple":     {"hp": 0,  "gold": 200,  "attack": 0},
    "Innovation Centre":    {"hp": 0,  "gold": 1000, "attack": 0},
    "Malpe Beach":          {"hp": 0,  "gold": 500,  "attack": 0},
    "Coin Circle":          {"hp": 0,  "gold": 150,  "attack": 0},
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
4. **MAJOR INFLUENCE**: Weave the player's academic Major (e.g., Computer Science, BioMedical, BioTechnology, Electronics and Communication, Mechanical) into the story narrative. For example, a CS student might face compiler errors or bad WiFi; BioMedical students face hospital/medical equipment issues; BioTechnology students face genetics/lab research scenarios; ECE students deal with circuit boards, microcontrollers, and wireless signals; Mechanical students deal with engines, workshops, and heavy tools.

*** CRITICAL STAT RULES ***
1. **OPTIONS MUST HAVE TAGS**: You MUST include tags in square brackets for any stat change.
   - CORRECT: "Eat Puff [+20 HP] [-20 Gold]"
   - WRONG: "Eat Puff"
2. **STORY VISUALS**: You may include stat tags in the story text as flavour (e.g. "You find a coin. [+250 Gold]"),
   but these are DISPLAY ONLY. The server manages all actual stat changes.

OUTPUT FORMAT (JSON ONLY, NO MARKDOWN):
{{
    "story": "Description...",
    "options": ["Opt 1 [+X HP]", "Opt 2", "Opt 3", "Opt 4"]
}}
"""

MAX_HISTORY_MESSAGES = 6  # 3 user + 3 assistant turns (sliding window)


def parse_tags(text):
    """Parse stat tags from button/rune text. Story tags are NEVER applied."""
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
    """Fuzzy-match a location string to LOCATION_STATS. Returns zero stats if not found."""
    for key in LOCATION_STATS:
        if key.lower() in location_name.lower():
            return dict(LOCATION_STATS[key])
    return {"hp": 0, "gold": 0, "attack": 0}

def get_random_items(count=3):
    if not ALL_ITEMS: return ""
    selected = random.sample(ALL_ITEMS, min(len(ALL_ITEMS), count))
    return ", ".join(selected)

def get_combat_options(game):
    options = [
        f"⚔️ Basic Attack [Damage: {game.attack}]",
        "🛡️ Defend & Heal [+25 HP]",
        f"⚡ Desperate Strike [-20 HP] [Damage: {int(game.attack * 2.5)}]"
    ]
    if game.gold >= 150:
        options.append("💰 Bribe [-150 Gold] [Damage: 50]")
    else:
        options.append("📣 Distract & Taunt [+5 Gold] [Damage: 15]")
    return options

def load_game_from_session(data):
    game = GameState()
    game.turn = data['turn']
    game.hp = data['hp']
    game.max_hp = data.get('max_hp', 100)
    game.gold = data['gold']
    game.attack = data.get('attack', 10)
    game.runes = data.get('runes', [])
    game.major = data.get('major', 'Undeclared')
    return game


@app.route('/')
def home():
    """Landing page — player chooses their AI provider and Major."""
    return render_template('index.html')


@app.route('/start', methods=['POST'])
def start():
    """Initialize a new game with the chosen AI provider and Major (Groq-only app)."""
    provider = request.json.get('provider', 'groq')
    major = request.json.get('major', 'Computer Science')
    
    if provider not in ('gemini', 'groq'):
        provider = 'groq'
        
    valid_majors = {
        'Computer Science':                  {"hp": 100, "max_hp": 100, "attack": 15, "gold": 500},
        'BioMedical':                        {"hp": 120, "max_hp": 120, "attack": 10, "gold": 600},
        'BioTechnology':                     {"hp": 110, "max_hp": 110, "attack": 12, "gold": 700},
        'Electronics and Communication':    {"hp": 100, "max_hp": 100, "attack": 13, "gold": 900},
        'Mechanical':                        {"hp": 115, "max_hp": 115, "attack": 11, "gold": 800}
    }
    
    if major not in valid_majors:
        major = 'Computer Science'
        
    stats = valid_majors[major]
    
    new_game = GameState()
    new_game.major = major
    new_game.hp = stats["hp"]
    new_game.max_hp = stats["max_hp"]
    new_game.attack = stats["attack"]
    new_game.gold = stats["gold"]

    session['provider'] = 'groq'
    session['major'] = major
    session['current_options'] = ["Start Adventure", "Check Inventory", "Rest", "Explore"]
    session['awaiting_rune'] = False
    session['short_history'] = []
    session['game_state'] = new_game.to_dict()

    return jsonify({
        "stats": new_game.to_dict(),
        "provider": 'groq',
        "major": major
    })


@app.route('/resume', methods=['POST'])
def resume():
    """Restore session variables from client-side auto-save backup (Groq-only app)."""
    data = request.json
    if not data or 'stats' not in data:
        return jsonify({"error": "Invalid resume data"}), 400

    session['provider'] = 'groq'
    session['major'] = data.get('stats', {}).get('major', 'Computer Science')
    session['current_options'] = data.get('options', [])
    session['awaiting_rune'] = data.get('awaiting_rune', False)
    session['short_history'] = data.get('short_history', [])
    session['game_state'] = data.get('stats')

    if data.get('boss'):
        session['active_boss'] = data.get('boss')
    else:
        session.pop('active_boss', None)

    return jsonify({"status": "success"})


@app.route('/action', methods=['POST'])
def action():
    data = session.get('game_state')
    if not data: return jsonify({"error": "No game found"}), 400

    game = load_game_from_session(data)
    user_choice = request.json.get('choice')

    # --- 1. COMBAT LOOP INTERCEPTION ---
    active_boss = session.get('active_boss')
    if active_boss:
        boss_name = active_boss["name"]
        boss_hp = active_boss["hp"]
        boss_max_hp = active_boss["max_hp"]
        boss_damage = active_boss["damage"]

        player_dmg = 0
        player_hp_change = 0
        player_gold_change = 0
        action_desc = ""

        if "Basic Attack" in user_choice:
            player_dmg = game.attack
            action_desc = f"You perform a Basic Attack, dealing {player_dmg} damage to {boss_name}."
        elif "Defend & Heal" in user_choice:
            player_hp_change = 25
            action_desc = f"You play defensively and focus on recovery, restoring {player_hp_change} HP."
        elif "Desperate Strike" in user_choice:
            player_hp_change = -20
            player_dmg = int(game.attack * 2.5)
            action_desc = f"You unleash a Desperate Strike, dealing {player_dmg} damage to {boss_name} but taking 20 strain damage!"
        elif "Bribe" in user_choice:
            player_gold_change = -150
            player_dmg = 50
            action_desc = f"You slide {boss_name} 150 Gold, dealing 50 damage through distraction!"
        elif "Distract & Taunt" in user_choice:
            player_gold_change = 5
            player_dmg = 15
            action_desc = f"You mock {boss_name}, dealing 15 damage and snatching 5 Gold from their desk!"

        boss_hp -= player_dmg
        if boss_hp < 0: boss_hp = 0

        game.update_stats({"hp": player_hp_change, "gold": player_gold_change})

        if boss_hp <= 0:
            session.pop('active_boss', None)
            game.turn += 1
            if game.turn > game.max_turns:
                game.is_game_over = True

            reward_gold = 500
            reward_atk = 20
            game.update_stats({"gold": reward_gold, "attack": reward_atk})

            victory_context = f"""
            Victory! The player has defeated the boss {boss_name}.
            Choice chosen: {user_choice}
            Action description: {action_desc}
            Reward received: +{reward_gold} Gold, +{reward_atk} ATK
            Next explore options are set. Narrative a short, celebratory wrap up of the battle.
            """
            
            short_history = session.get('short_history', [])
            try:
                messages = [{"role": "system", "content": SYSTEM_PROMPT}]
                for msg in short_history:
                    groq_role = "assistant" if msg["role"] == "model" else "user"
                    messages.append({"role": groq_role, "content": msg["parts"][0]})
                messages.append({"role": "user", "content": victory_context})
                
                client = get_groq_client()
                response = client.chat.completions.create(
                    model=GROQ_MODEL,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0.8,
                    max_tokens=1024,
                )
                response_text = response.choices[0].message.content
                ai_data = json.loads(response_text)
                story_msg = ai_data["story"]
                next_options = ai_data["options"]
            except Exception as e:
                story_msg = f"🏆 VICTORY! You defeated {boss_name}! (+500 Gold, +20 ATK)"
                next_options = ["Continue Semester", "Explore Campus", "Rest in Hostel", "Go to Library"]

            session['short_history'] = []
            session['current_options'] = next_options
            session['game_state'] = game.to_dict()

            return jsonify({
                "message": story_msg,
                "stats": game.to_dict(),
                "options": next_options,
                "awaiting_rune": session.get('awaiting_rune', False)
            })

        boss_counter_dmg = boss_damage
        if "Defend & Heal" in user_choice:
            boss_counter_dmg = int(boss_damage * 0.4)
            
        game.update_stats({"hp": -boss_counter_dmg})

        if game.hp <= 0:
            game.is_game_over = True
            session.pop('active_boss', None)
            defeat_context = f"""
            Defeat! The player was killed in combat by {boss_name}.
            Choice chosen: {user_choice}
            Action description: {action_desc}
            Final fatal hit from boss: -{boss_counter_dmg} HP
            Generate a short, dramatic/humorous game-over description of how the player failed their semester.
            """
            short_history = session.get('short_history', [])
            try:
                messages = [{"role": "system", "content": SYSTEM_PROMPT}]
                for msg in short_history:
                    groq_role = "assistant" if msg["role"] == "model" else "user"
                    messages.append({"role": groq_role, "content": msg["parts"][0]})
                messages.append({"role": "user", "content": defeat_context})
                
                client = get_groq_client()
                response = client.chat.completions.create(
                    model=GROQ_MODEL,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0.8,
                    max_tokens=1024,
                )
                response_text = response.choices[0].message.content
                ai_data = json.loads(response_text)
                story_msg = ai_data["story"]
            except Exception as e:
                story_msg = f"💀 WASTED. You were defeated by {boss_name}."

            session['current_options'] = []
            session['game_state'] = game.to_dict()
            return jsonify({
                "message": story_msg,
                "stats": game.to_dict(),
                "options": []
            })

        active_boss["hp"] = boss_hp
        session['active_boss'] = active_boss

        combat_context = f"""
        COMBAT ROUND IN PROGRESS.
        Player is fighting: {boss_name} (HP: {boss_hp}/{boss_max_hp})
        Player action: {action_desc}
        Boss response: Attacks back dealing {boss_counter_dmg} HP damage.
        Current Player HP: {game.hp}/{game.max_hp}
        Narrate this combat round in a single short paragraph. Do not finish the fight yet.
        """

        short_history = session.get('short_history', [])
        combat_options = get_combat_options(game)
        try:
            messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            for msg in short_history:
                groq_role = "assistant" if msg["role"] == "model" else "user"
                messages.append({"role": groq_role, "content": msg["parts"][0]})
            messages.append({"role": "user", "content": combat_context})
            
            client = get_groq_client()
            response = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.8,
                max_tokens=1024,
            )
            response_text = response.choices[0].message.content
            ai_data = json.loads(response_text)
            story_msg = ai_data["story"]
        except Exception as e:
            story_msg = f"⚔️ Combat continues! {action_desc} {boss_name} strikes back for {boss_counter_dmg} damage!"

        session['current_options'] = combat_options
        session['game_state'] = game.to_dict()

        return jsonify({
            "message": story_msg,
            "stats": game.to_dict(),
            "options": combat_options,
            "boss": {
                "name": boss_name,
                "hp": boss_hp,
                "max_hp": boss_max_hp
            },
            "awaiting_rune": session.get('awaiting_rune', False)
        })

    # --- 2. TRIGGER BOSS FIGHT ---
    if game.turn in [10, 20, 30, 40, 50] and not session.get('active_boss') and not session.get('awaiting_rune'):
        if game.turn == 50:
            boss_name = "Anil Rana, The Director (FINAL BOSS)"
            boss_max_hp = int(50 * 12 + game.attack * 3.5)
            boss_dmg = 75
        else:
            boss_name = random.choice(ALL_ENEMIES) if ALL_ENEMIES else "The Strict Invigilator"
            boss_max_hp = int(game.turn * 12 + game.attack * 2.5)
            boss_dmg = int(game.turn * 1.5)
            
        active_boss = {
            "name": boss_name,
            "hp": boss_max_hp,
            "max_hp": boss_max_hp,
            "damage": boss_dmg
        }
        session['active_boss'] = active_boss
        
        appear_context = f"""
        BOSS ENCOUNTER TRIGGERED!
        The legendary boss/enemy appeared: {boss_name} (Max HP: {boss_max_hp}, Damage: {boss_dmg})
        Player is a {game.major} major.
        Describe their epic, humorous, or terrifying arrival at the campus location.
        Prompt the player that battle has begun.
        """
        
        short_history = session.get('short_history', [])
        combat_options = get_combat_options(game)
        try:
            messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            for msg in short_history:
                groq_role = "assistant" if msg["role"] == "model" else "user"
                messages.append({"role": groq_role, "content": msg["parts"][0]})
            messages.append({"role": "user", "content": appear_context})
            
            client = get_groq_client()
            response = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.8,
                max_tokens=1024,
            )
            response_text = response.choices[0].message.content
            ai_data = json.loads(response_text)
            story_msg = ai_data["story"]
        except Exception as e:
            story_msg = f"⚠️ WARNING: A wild {boss_name} appears! Battle begins!"
            
        session['current_options'] = combat_options
        session['game_state'] = game.to_dict()
        
        return jsonify({
            "message": story_msg,
            "stats": game.to_dict(),
            "options": combat_options,
            "boss": {
                "name": boss_name,
                "hp": boss_max_hp,
                "max_hp": boss_max_hp
            },
            "awaiting_rune": session.get('awaiting_rune', False)
        })

    # --- 3. STANDARD TURN EXECUTION ---
    button_stats = parse_tags(user_choice)

    # --- RUNE SELECTION LOGIC ---
    if session.get('awaiting_rune'):
        game.runes.append(user_choice)
        game.update_stats(button_stats)
        game.turn += 1
        session['awaiting_rune'] = False

        bridge_story = f"You absorb the power of the {user_choice}! You feel invincible."
        next_options = ["Continue Adventure", "Check Stats", "Roar", "Look for Enemies"]

        session['current_options'] = next_options
        session['game_state'] = game.to_dict()
        return jsonify({
            "message": bridge_story,
            "stats": game.to_dict(),
            "options": next_options,
            "awaiting_rune": session.get('awaiting_rune', False)
        })

    # --- CHECK GOLD AFFORDABILITY ---
    gold_cost = button_stats.get('gold', 0)
    if gold_cost < 0 and (game.gold + gold_cost < 0):
        old_options = session.get('current_options', [])
        return jsonify({
            "message": f"🚫 You check your wallet... only {game.gold} Gold. You need {abs(gold_cost)} Gold!",
            "stats": game.to_dict(),
            "options": old_options,
            "awaiting_rune": session.get('awaiting_rune', False)
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
            "options": rune_options,
            "awaiting_rune": session.get('awaiting_rune', False)
        })

    # --- APPLY BUTTON STATS (player's explicit choice) ---
    game.update_stats(button_stats)

    # --- NARRATIVE OVERRIDE: Server applies location stats directly ---
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
    Major: {game.major}
    Choice: {user_choice}
    SUGGESTED LOOT: {suggested_loot}
    {special_instruction}
    {bonus_desc}
    """

    # Build Groq message history from sliding window
    short_history = session.get('short_history', [])

    # Convert sliding window to Groq's message format
    # Groq uses OpenAI-compatible format: [{"role": "user"/"assistant", "content": "..."}]
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in short_history:
        # short_history stores {"role": "user"/"model", "parts": ["..."]}
        # Groq expects {"role": "user"/"assistant", "content": "..."}
        groq_role = "assistant" if msg["role"] == "model" else "user"
        messages.append({"role": groq_role, "content": msg["parts"][0]})
    messages.append({"role": "user", "content": turn_context})

    try:
        client = get_groq_client()
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            response_format={"type": "json_object"},  # Groq's JSON mode
            temperature=0.8,  # Slightly creative for RPG storytelling
            max_tokens=1024,
        )

        response_text = response.choices[0].message.content
        ai_data = json.loads(response_text)

        # Stats already applied above (button + location). Story is narration only.
        game.turn += 1

        if game.turn > game.max_turns:
            game.is_game_over = True

        # Update sliding window
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
            "options": ai_data["options"],
            "awaiting_rune": session.get('awaiting_rune', False)
        })

    except Exception as e:
        error_msg = f"Connection Error (Groq): {str(e)}"
        print(f"AI Error: {e}")
        return jsonify({
            "message": error_msg,
            "stats": game.to_dict(),
            "options": session.get('current_options', []),
            "awaiting_rune": session.get('awaiting_rune', False)
        })

if __name__ == '__main__':
    app.run(debug=True)
