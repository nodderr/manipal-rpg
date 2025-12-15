import json

class GameState:
    def __init__(self):
        self.turn = 1
        self.max_turns = 50
        self.hp = 100
        self.max_hp = 100  # Starts at 100
        self.gold = 0
        self.attack = 10
        self.inventory = []
        self.runes = []
        self.history = []
        self.is_game_over = False
    
    def to_dict(self):
        return {
            "turn": self.turn,
            "hp": self.hp,
            "max_hp": self.max_hp, # Important: Save this to session
            "gold": self.gold,
            "attack": self.attack,
            "inventory": self.inventory,
            "runes": self.runes,
            "history": self.history,
            "is_game_over": self.is_game_over
        }

    def update_stats(self, changes):
        # --- 1. HP & MAX HP LOGIC ---
        hp_change = changes.get("hp", 0)
        
        if hp_change > 0:
            # HEALING / BUFF:
            # Rule: If items/events give HP, it increases BOTH Current and Max HP permanently.
            self.max_hp += hp_change
            self.hp += hp_change
        else:
            # DAMAGE:
            # Rule: Only reduces Current HP.
            self.hp += hp_change

        # Sanity Check: Current HP cannot exceed Max HP (unless we just buffed it above)
        if self.hp > self.max_hp:
            self.hp = self.max_hp

        # --- 2. GOLD ---
        gold_change = changes.get("gold", 0)
        self.gold += gold_change
            
        # --- 3. ATTACK ---
        atk_change = changes.get("attack", 0)
        self.attack += atk_change
        if self.attack < 1:
            self.attack = 1

        # --- GAME OVER CHECKS ---
        if self.hp <= 0:
            self.hp = 0
            self.is_game_over = True
            return

        self.turn += 1
        if self.turn > self.max_turns:
            self.is_game_over = True