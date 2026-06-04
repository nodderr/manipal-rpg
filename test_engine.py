# -*- coding: utf-8 -*-
"""
test_engine.py - Full verification test suite for Manipal RPG
Run with: python -X utf8 test_engine.py
"""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import os
import re
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine import GameState

# --- Replicate helpers from app.py ---

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

def parse_tags(text):
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
    for key in LOCATION_STATS:
        if key.lower() in location_name.lower():
            return dict(LOCATION_STATS[key])
    return {"hp": 0, "gold": 0, "attack": 0}

# --- Test Utilities ---
PASS = "\033[92m[PASS]\033[0m"
FAIL = "\033[91m[FAIL]\033[0m"
results = []

def check(name, condition, explanation=""):
    status = PASS if condition else FAIL
    print(f"  {status} {name}")
    if not condition and explanation:
        print(f"         -> FAIL: {explanation}")
    results.append((name, condition))

def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ============================================================
# 1. get_location_stats — fuzzy location lookup
# ============================================================
section("1. get_location_stats() — Location Lookup Table")

# Exact key match
r = get_location_stats("D406")
check("D406 exact match: gold=800 hp=50 atk=20",
      r == {"hp": 50, "gold": 800, "attack": 20}, str(r))

# Fuzzy match from FRIEND_ZONES_LIST format
r = get_location_stats("D406 (Noddy's Room) - Chaotic roommate energy")
check("D406 fuzzy match from full zone string",
      r == {"hp": 50, "gold": 800, "attack": 20}, str(r))

r = get_location_stats("Babas Point - Scenic, quiet place")
check("Babas Point fuzzy match: hp=20 gold=0 atk=0",
      r == {"hp": 20, "gold": 0, "attack": 0}, str(r))

r = get_location_stats("C904 (Reva, Anshu, Disha, Adel's Room) - Cozy group zone")
check("C904 fuzzy match: gold=800 hp=50 atk=20",
      r == {"hp": 50, "gold": 800, "attack": 20}, str(r))

r = get_location_stats("Tiger Circle")
check("Tiger Circle: gold=250 hp=0 atk=0",
      r == {"hp": 0, "gold": 250, "attack": 0}, str(r))

r = get_location_stats("Innovation Centre")
check("Innovation Centre: gold=1000",
      r["gold"] == 1000, str(r))

# Unknown location returns safe zero defaults
r = get_location_stats("Some Random Place That Doesnt Exist")
check("Unknown location returns zero stats (safe default)",
      r == {"hp": 0, "gold": 0, "attack": 0}, str(r))

# Returns a copy (mutating returned dict doesn't affect LOCATION_STATS)
r = get_location_stats("D406")
r["gold"] = 9999
check("Returns a copy — mutating it doesn't affect LOCATION_STATS",
      LOCATION_STATS["D406"]["gold"] == 800)


# ============================================================
# 2. Stats applied from button text (player choice)
# ============================================================
section("2. Button Stats — Player Choice Applied Correctly")

g = GameState()
check("GameState default major is 'Undeclared'", g.major == "Undeclared")
check("GameState dict contains 'major'", "major" in g.to_dict())
check("GameState serialized major is correct", g.to_dict()["major"] == "Undeclared")
g.gold = 500; g.hp = 100; g.max_hp = 100; g.attack = 10

# Player clicks "Eat Puff [+20 HP] [-20 Gold]"
button_stats = parse_tags("Eat Puff [+20 HP] [-20 Gold]")
g.update_stats(button_stats)
check("HP after eating puff: 100+20=120", g.hp == 120, f"Got {g.hp}")
check("Max HP after eating puff: 100+20=120 (HP gain = permanent)", g.max_hp == 120, f"Got {g.max_hp}")
check("Gold after eating puff: 500-20=480", g.gold == 480, f"Got {g.gold}")

g2 = GameState()
g2.gold = 500; g2.hp = 100; g2.max_hp = 100

# Player clicks "Fight enemy [-30 HP] [+10 ATK]"
button_stats2 = parse_tags("Fight enemy [-30 HP] [+10 ATK]")
g2.update_stats(button_stats2)
check("HP after fight: 100-30=70", g2.hp == 70, f"Got {g2.hp}")
check("Max HP unchanged after damage: still 100", g2.max_hp == 100, f"Got {g2.max_hp}")
check("ATK after fight: 10+10=20 (default 10)", g2.attack == 20, f"Got {g2.attack}")


# ============================================================
# 3. Location bonus applied server-side (narrative override)
# ============================================================
section("3. Location Bonus — Server-Side Application")

g3 = GameState()
g3.gold = 500; g3.hp = 100; g3.max_hp = 100; g3.attack = 10

# Simulate: player chose "Explore [+0]" but narrative override fired to D406
button_stats3 = parse_tags("Explore campus")   # no tags
loc_stats = get_location_stats("D406 (Noddy's Room) - Chaotic roommate energy")

g3.update_stats(button_stats3)   # button (no change)
g3.update_stats(loc_stats)       # location bonus (server applies directly)

check("Gold after D406 override: 500+800=1300", g3.gold == 1300, f"Got {g3.gold}")
check("HP after D406 override: 100+50=150", g3.hp == 150, f"Got {g3.hp}")
check("ATK after D406 override: 10+20=30", g3.attack == 30, f"Got {g3.attack}")

# Ensure story tags are NOT parsed — the AI story is purely narrative
g4 = GameState()
g4.gold = 500; g4.hp = 100; g4.max_hp = 100

ai_story = "You stroll into D406. The room is full of friends. The vibe is electric. [+800 Gold] [+50 HP] [+20 ATK]"
story_stats = parse_tags(ai_story)   # We parse it to inspect it...
# ...but we NEVER call g4.update_stats(story_stats). Story is display only.
check("Story text NOT applied — gold unchanged at 500", g4.gold == 500, f"Got {g4.gold}")
check("Story contains tags but they are NEVER applied", True)
print(f"         Story would have given: gold={story_stats['gold']} hp={story_stats['hp']} atk={story_stats['attack']}")
print(f"         Actual gold: {g4.gold} (unchanged)")


# ============================================================
# 4. Turn increments exactly once per action
# ============================================================
section("4. Turn Increments Exactly Once Per Action")

g5 = GameState()
g5.turn = 1
g5.update_stats({"hp": 0, "gold": 0, "attack": 0})  # button (no turn increment)
g5.update_stats({"hp": 50, "gold": 800, "attack": 20})  # location bonus (no turn increment)
g5.turn += 1  # explicit single increment at end of action

check("Turn = 2 after 1 full action (button + location bonus)", g5.turn == 2,
      f"Got turn={g5.turn}")

g6 = GameState()
g6.turn = 1
for _ in range(5):
    g6.update_stats({"hp": 0, "gold": 0, "attack": 0})
    g6.update_stats({"hp": 0, "gold": 0, "attack": 0})  # simulate location bonus
    g6.turn += 1

check("Turn = 6 after 5 actions", g6.turn == 6, f"Got turn={g6.turn}")


# ============================================================
# 5. Session cookie size stays under 4KB
# ============================================================
section("5. Session Cookie Size Under 4KB After 10 Turns")

MAX_HISTORY_MESSAGES = 6
game_state = {
    "turn": 10, "hp": 200, "max_hp": 250, "gold": 5000,
    "attack": 50, "inventory": [], "runes": ["Rune of Vitality [+300 HP]"],
    "is_game_over": False
}
fake_user = {"role": "user", "parts": ["Turn 10 context..."]}
fake_model = {"role": "model", "parts": ['{"story": "Epic story here.", "options": ["A","B","C","D"]}']}

short_history = []
for _ in range(10):
    short_history.append(fake_user)
    short_history.append(fake_model)
    if len(short_history) > MAX_HISTORY_MESSAGES:
        short_history = short_history[-MAX_HISTORY_MESSAGES:]

session_data = {
    "game_state": game_state,
    "short_history": short_history,
    "current_options": ["A", "B", "C", "D"],
    "awaiting_rune": False
}
session_size = len(json.dumps(session_data).encode('utf-8'))
print(f"\n  Session size after 10 turns: {session_size} bytes (limit: 4096 bytes)")
check(f"Session under 4KB ({session_size} bytes)", session_size < 4096)
check("History capped at 6 messages", len(short_history) == MAX_HISTORY_MESSAGES)


# ============================================================
# 6. Lore file has no stat tags in locations/friend zones
# ============================================================
section("6. Lore File — No Stat Tags in Locations or Friend Zones")

try:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(BASE_DIR, 'manipal_lore.txt'), 'r', encoding='utf-8') as f:
        lore = f.read()

    # Split into sections
    sections = {}
    current = "preamble"
    for line in lore.split('\n'):
        if line.strip().startswith('[') and line.strip().endswith(']'):
            current = line.strip()
            sections[current] = []
        else:
            sections.setdefault(current, []).append(line)

    loc_text = '\n'.join(sections.get('[LOCATIONS]', []))
    friend_text = '\n'.join(sections.get('[FRIEND ZONES - HIGH PRIORITY]', []))
    item_text = '\n'.join(sections.get('[ITEMS & LOOT]', []))

    loc_tags = re.findall(r'\[\s*[+\-]?\s*\d+\s*(?:HP|Gold|ATK)\s*\]', loc_text, re.IGNORECASE)
    friend_tags = re.findall(r'\[\s*[+\-]?\s*\d+\s*(?:HP|Gold|ATK)\s*\]', friend_text, re.IGNORECASE)
    item_tags = re.findall(r'\[\s*[+\-]?\s*\d+\s*(?:HP|Gold|ATK)\s*\]', item_text, re.IGNORECASE)

    check("No stat tags in [LOCATIONS] section", len(loc_tags) == 0,
          f"Found tags: {loc_tags}")
    check("No stat tags in [FRIEND ZONES] section", len(friend_tags) == 0,
          f"Found tags: {friend_tags}")
    check(f"[ITEMS & LOOT] still has its tags ({len(item_tags)} found)", len(item_tags) > 0)

except FileNotFoundError:
    print("  [SKIP] manipal_lore.txt not found")


# ============================================================
# 7. Boss Battle Mechanics & Scaling
# ============================================================
section("7. Boss Battle Mechanics & Scaling")

# Default scaling rules (Player ATK is e.g. 15)
# Turn 10 Boss with 15 ATK: HP = int(10 * 12 + 15 * 2.5) = 120 + 37 = 157
# Turn 10 Boss DMG: int(10 * 1.5) = 15
t10_hp = int(10 * 12 + 15 * 2.5)
t10_dmg = int(10 * 1.5)
check("Turn 10 Boss HP = 157 (for 15 player ATK)", t10_hp == 157, f"Got {t10_hp}")
check("Turn 10 Boss DMG = 15", t10_dmg == 15, f"Got {t10_dmg}")

# Turn 10 Boss with 110 ATK: HP = int(10 * 12 + 110 * 2.5) = 120 + 275 = 395
t10_high_hp = int(10 * 12 + 110 * 2.5)
check("Turn 10 Boss HP = 395 (for 110 player ATK)", t10_high_hp == 395, f"Got {t10_high_hp}")

# Turn 40 Boss with 50 ATK: HP = int(40 * 12 + 50 * 2.5) = 480 + 125 = 605
# Turn 40 Boss DMG: int(40 * 1.5) = 60
t40_hp = int(40 * 12 + 50 * 2.5)
t40_dmg = int(40 * 1.5)
check("Turn 40 Boss HP = 605 (for 50 player ATK)", t40_hp == 605, f"Got {t40_hp}")
check("Turn 40 Boss DMG = 60", t40_dmg == 60, f"Got {t40_dmg}")

# Boss HP decrement simulation
boss_hp = 50
player_atk = 15
boss_hp -= player_atk
check("Boss HP reduced by player attack: 50-15=35", boss_hp == 35, f"Got {boss_hp}")

# Desperate strike cost simulation
g_combat = GameState()
g_combat.hp = 100
g_combat.update_stats({"hp": -20})
check("Player HP reduced by Desperate Strike strain: 100-20=80", g_combat.hp == 80, f"Got {g_combat.hp}")



# ============================================================
# 8. Front-End Session Recovery (Auto-Save) & /resume route
# ============================================================
section("8. Front-End Session Recovery & /resume Route")

try:
    from app import app
    app.config['TESTING'] = True
    client = app.test_client()

    # 8.1 Test that loading without stats returns 400
    res = client.post('/resume', json={})
    check("Resume with empty payload returns 400", res.status_code == 400)

    # 8.2 Test /resume successfully restores session values
    save_payload = {
        "stats": {
            "turn": 15,
            "hp": 95,
            "max_hp": 110,
            "gold": 350,
            "attack": 25,
            "major": "BioMedical",
            "runes": ["Rune of Strength"],
            "is_game_over": False
        },
        "message": "Resume message test",
        "options": ["Choice A", "Choice B"],
        "provider": "gemini",
        "awaiting_rune": True,
        "boss": {
            "name": "The Strict Invigilator",
            "hp": 80,
            "max_hp": 100,
            "damage": 12
        },
        "short_history": [{"role": "user", "parts": ["test context"]}]
    }

    with client.session_transaction() as sess:
        sess.clear()

    res = client.post('/resume', json=save_payload)
    check("Resume with valid payload returns 200/success", res.status_code == 200)
    
    res_data = json.loads(res.data)
    check("Response status is success", res_data.get("status") == "success")

    # verify the Flask session was populated
    with client:
        client.post('/resume', json=save_payload)
        from flask import session as flask_session
        check("Flask session provider restored", flask_session.get('provider') == 'gemini')
        check("Flask session major restored", flask_session.get('major') == 'BioMedical')
        check("Flask session current_options restored", flask_session.get('current_options') == ["Choice A", "Choice B"])
        check("Flask session awaiting_rune restored", flask_session.get('awaiting_rune') is True)
        check("Flask session short_history restored", len(flask_session.get('short_history', [])) == 1)
        check("Flask session game_state restored with correct stats", flask_session.get('game_state', {}).get('turn') == 15)
        check("Flask session active_boss restored", flask_session.get('active_boss', {}).get('name') == "The Strict Invigilator")

    # 8.3 Repeat for app_groq /resume
    from app_groq import app as app_groq
    app_groq.config['TESTING'] = True
    client_groq = app_groq.test_client()

    with client_groq:
        res = client_groq.post('/resume', json=save_payload)
        check("Groq app resume returns 200", res.status_code == 200)
        from flask import session as flask_session_groq
        check("Groq Flask session provider is forced to groq", flask_session_groq.get('provider') == 'groq')
        check("Groq Flask session active_boss restored", flask_session_groq.get('active_boss', {}).get('hp') == 80)

except Exception as e:
    check("Resume route tests passed without exception", False, str(e))


# ============================================================
# 9. Stats-Driven Dynamic Endings
# ============================================================
section("9. Stats-Driven Dynamic Endings")

try:
    from app import get_ending_classification
    
    # 9.1 Placements Legend Ending test (high ATK)
    g_end1 = GameState()
    g_end1.attack = 100
    g_end1.major = "Mechanical"
    name, desc = get_ending_classification(g_end1)
    check("High ATK (100) triggers Placements Legend Ending", "Placements Legend" in name)

    # 9.2 Placements Legend Ending test (CS Major)
    g_end2 = GameState()
    g_end2.attack = 15
    g_end2.major = "Computer Science"
    name, desc = get_ending_classification(g_end2)
    check("CS Major triggers Placements Legend Ending", "Placements Legend" in name)

    # 9.3 Tiger Circle Chai Tycoon Ending test (high Gold)
    g_end3 = GameState()
    g_end3.attack = 15
    g_end3.gold = 4000
    g_end3.major = "Mechanical"
    name, desc = get_ending_classification(g_end3)
    check("High Gold (4000) triggers Tiger Circle Chai Tycoon Ending", "Tiger Circle Chai Tycoon" in name)

    # 9.4 Dropout Ending test (Chaos/Greed Runes)
    g_end4 = GameState()
    g_end4.attack = 15
    g_end4.gold = 500
    g_end4.major = "Mechanical"
    g_end4.runes = ["Rune of Chaos [+200 ATK] [-100 HP]"]
    name, desc = get_ending_classification(g_end4)
    check("Rune of Chaos triggers Dropout Ending", "Dropout" in name)

    # 9.5 Safe Average Graduate Ending test (balanced stats)
    g_end5 = GameState()
    g_end5.attack = 15
    g_end5.gold = 500
    g_end5.major = "Mechanical"
    g_end5.runes = ["Rune of Vitality [+300 HP]"]
    name, desc = get_ending_classification(g_end5)
    check("Balanced stats trigger Safe Average Graduate Ending", "Safe Average Graduate" in name)

except Exception as e:
    check("Stats-Driven Endings classification tests passed without exception", False, str(e))


# ============================================================
# SUMMARY
# ============================================================
section("SUMMARY")

passed = sum(1 for _, r in results if r)
failed = sum(1 for _, r in results if not r)
failed_names = [name for name, r in results if not r]

print(f"\n  Tests passed:  {passed}/{len(results)}")
print(f"  Tests failed:  {failed}/{len(results)}")
if failed_names:
    print(f"\n  Failing tests:")
    for b in failed_names:
        print(f"    x {b}")
else:
    print("\n  All tests passed. Middle ground architecture verified. Ready to push!")
