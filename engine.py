import json

class GameState:
    def __init__(self):
        self.turn = 1
        self.max_turns = 50
        self.hp = 100
        self.max_hp = 100
        self.gold = 0
        self.attack = 10
        self.inventory = []
        self.history = []
        self.is_game_over = False
    
    def to_dict(self):
        return {
            "turn": self.turn,
            "hp": self.hp,
            "max_hp": self.max_hp,
            "gold": self.gold,
            "attack": self.attack,
            "inventory": self.inventory,
            "history": self.history,
            "is_game_over": self.is_game_over
        }

    def update_stats(self, changes):
        if "hp" in changes:
            self.hp += changes["hp"]
            self.hp = min(self.hp, self.max_hp)
        
        if "gold" in changes:
            self.gold += changes["gold"]
            
        if "attack" in changes:
            self.attack += changes["attack"]
            if self.attack < 1:
                self.attack = 1

        if self.hp <= 0:
            self.hp = 0
            self.is_game_over = True
            return

        self.turn += 1
        if self.turn > self.max_turns:
            self.is_game_over = True
