import os
import json
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

client = Groq(
    api_key=os.getenv("GROQ_API_KEY"),
)

try:
    with open('manipal_lore.txt', 'r', encoding='utf-8') as f:
        CAMPUS_DATA = f.read()
except FileNotFoundError:
    CAMPUS_DATA = "Location: A generic university campus."

SYSTEM_PROMPT = f"""
You are the Dungeon Master for a fast-paced text RPG set in **Manipal (MAHE Campus)**.

WORLD DATA:
{CAMPUS_DATA}

RULES:
1. The game ends at Turn 50.
2. EVERY 10th Turn MUST be a BOSS FIGHT.
3. Provide exactly 4 distinct options.
4. If the User's choice includes a stat tag (e.g., "[+10 HP]"), you MUST apply that change.

CRITICAL WRITING STYLE:
- KEEP IT SHORT. Max 2-3 sentences.

OUTPUT FORMAT (JSON ONLY):
{{
    "story": "Short description...",
    "hp_change": 0,
    "gold_change": 0,
    "attack_change": 0,
    "options": ["Opt 1 [+X HP]", "Opt 2", "Opt 3", "Opt 4"]
}}
"""

def clean_json(text):
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text

@app.route('/')
def home():
    new_game = GameState()
    new_game.history = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]
    session['game_state'] = new_game.to_dict()
    return render_template('index.html', stats=new_game.to_dict())

@app.route('/action', methods=['POST'])
def action():
    data = session.get('game_state')
    if not data:
        return jsonify({"error": "No game found - Please refresh"}), 400
    
    game = GameState()
    game.turn = data['turn']
    game.hp = data['hp']
    game.gold = data['gold']
    game.attack = data.get('attack', 10)
    game.history = data.get('history', [])

    user_choice = request.json.get('choice')

    is_boss_turn = (game.turn % 10 == 0)
    special_instruction = ""
    if is_boss_turn:
        special_instruction = f"⚠️ CRITICAL: TURN {game.turn} IS A BOSS FIGHT!"

    turn_context = f"""
    Current Turn: {game.turn}
    HP: {game.hp}
    Gold: {game.gold}
    Attack Power: {game.attack}
    Player's Choice: {user_choice}
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
        
        game.update_stats({
            "hp": ai_data.get("hp_change", 0),
            "gold": ai_data.get("gold_change", 0),
            "attack": ai_data.get("attack_change", 0)
        })
        
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
            "message": "Connection error. Please try again.",
            "stats": game.to_dict(),
            "options": ["Retry Action"]
        })

if __name__ == '__main__':
    app.run(debug=True)
