# -*- coding: utf-8 -*-
"""
test_stat_source.py - Diagnose the "AI hallucinates stats" issue
Run with: python -X utf8 test_stat_source.py
"""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import re

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

PASS = "\033[92m[PASS]\033[0m"
FAIL = "\033[91m[FAIL]\033[0m"

def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

section("THE ACTUAL ROOT CAUSE OF INCONSISTENT STATS")

print("""
PROBLEM: After the last fix, stats come ONLY from the AI story text.
But the lore file (manipal_lore.txt) is fed directly into the system prompt.
The lore contains stat tags embedded in location/friend-zone descriptions:

  D406: [+800 Gold] [+50 HP] [+20 ATK]
  TC:   [+250 Gold]
  IC:   [+1000 Gold]

40% of turns, a NARRATIVE OVERRIDE forces the player to a location.
The AI reads the lore, sees those tags, and includes them in the story.
Our parser then applies those tags — but the player NEVER CHOSE that action.
""")

section("PROOF: Stat tags the AI is reading from lore context")

# What the AI sees in its context when a NARRATIVE OVERRIDE fires
narrative_override_examples = [
    ("D406 override",
     "You stumble into D406 (Noddy's Room). Chaotic energy fills the air. [+800 Gold] [+50 HP] [+20 ATK]",
     800, 50, 20),
    ("IC override",
     "You enter the Innovation Centre. You win a hackathon prize! [+1000 Gold]",
     1000, 0, 0),
    ("Tiger Circle override",
     "You find yourself at Tiger Circle. A lost wallet lies on the ground. [+250 Gold]",
     250, 0, 0),
    ("Malpe Beach override",
     "You're transported to Malpe Beach. You find a rare shell and sell it. [+500 Gold]",
     500, 0, 0),
]

print("\n  Stat changes silently applied by AI story text when narrative overrides fire:")
print(f"  {'Location':<25} {'Gold':>8} {'HP':>6} {'ATK':>6}")
print(f"  {'-'*25} {'-'*8} {'-'*6} {'-'*6}")
for name, story, exp_gold, exp_hp, exp_atk in narrative_override_examples:
    parsed = parse_tags(story)
    print(f"  {name:<25} {parsed['gold']:>+8} {parsed['hp']:>+6} {parsed['attack']:>+6}")

print("""
  These fire on 40% of turns, regardless of what the player chose.
  The player clicks "Fight the enemy" and randomly gets +800 Gold
  because a narrative override moved them to D406 in the background.
  This is why stats look random/hallucinated.
""")

section("THE CORRECT ARCHITECTURE")

print("""
  There are TWO separate things the game needs:
  
  1. PLAYER-CHOSEN STATS (deterministic):
     The player picks "Eat Puff [+20 HP] [-20 Gold]"
     -> Apply exactly +20 HP and -20 Gold. Period.
     -> Button tags are the contract. Apply them from the button.

  2. NARRATIVE FLAVOR (display only):
     The AI writes "You devour the puff eagerly. [+20 HP]"
     -> This [+20 HP] in the story is COSMETIC — it visually
        confirms what the button already applied. DO NOT apply again.
     -> Never parse story tags for stat changes.

  The lore's location tags ([+800 Gold] on D406) are there so the AI
  can describe WHY a place gives bonuses. They should be stripped from
  the lore file so the AI cannot accidentally echo them into the story.
  
  FIXES NEEDED:
  A. Strip stat tags from manipal_lore.txt (locations + friend zones)
     so the AI stops hallucinating location bonuses into story text.
  B. Apply stats from button text ONLY — not from story text at all.
  C. Story text is purely narrative/flavor. Never parsed for stats.
""")

section("SIMULATING THE FIXED VS BUGGY FLOW")

gold = 500
print(f"\n  Starting gold: {gold}")

# BUGGY: stats come only from story (current code)
player_choice = "Fight the enemy [-10 HP]"
ai_story_with_override = "You charge at the enemy! Suddenly you find yourself at D406 (Noddy's Room)! [+800 Gold] [+50 HP] [+20 ATK] The fight ends mysteriously."
story_stats = parse_tags(ai_story_with_override)
gold_buggy = gold + story_stats['gold']
print(f"  BUGGY (story-only):  clicked '{player_choice}' -> gold jumps to {gold_buggy} (AI added D406 bonus!)")

# FIXED: stats come only from button text
button_stats = parse_tags(player_choice)
gold_fixed = gold + button_stats['gold']
print(f"  FIXED (button-only): clicked '{player_choice}' -> gold stays {gold_fixed} (correct, player chose fight)")

print(f"""
  Summary:
  - Player chose a fight action, expected no gold change
  - Buggy code: gold jumped from {gold} to {gold_buggy} (+{story_stats['gold']}) due to D406 narrative override
  - Fixed code: gold stays at {gold_fixed} (only button stats applied)
""")
