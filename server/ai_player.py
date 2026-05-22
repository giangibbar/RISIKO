"""AI player logic for Risiko — difficulty-based decision making with strategic intelligence."""

import random
from typing import List, Tuple, Dict, Optional

from .models import GameState, GamePhase, Card, CardSymbol
from .map_data import get_neighbors, CONTINENTS, CONTINENT_BONUSES
from .combat import max_attacker_dice
from .cards import is_valid_set, calculate_trade_bonus


# --- CARD MEMORY ---

class CardMemory:
    """Tracks cards traded by opponents to estimate remaining deck composition."""

    def __init__(self):
        self.traded_cards: List[Dict] = []  # {player_id, symbols, turn}
        self.total_sets_seen: int = 0

    def record_trade(self, player_id: int, turn: int):
        """Record that a player traded cards (we don't see which, but track the event)."""
        self.traded_cards.append({"player_id": player_id, "turn": turn})
        self.total_sets_seen += 1

    def estimate_opponent_cards(self, game_state: GameState, my_id: int) -> Dict[int, int]:
        """Estimate how many cards each opponent likely has."""
        estimates = {}
        for p in game_state.players:
            if p.id == my_id or not p.alive:
                continue
            # We can see card count (it's public info in Risiko)
            estimates[p.id] = len(p.cards)
        return estimates

    def opponent_near_trade(self, game_state: GameState, my_id: int) -> List[int]:
        """Return IDs of opponents who likely have 4+ cards (about to get bonus troops)."""
        dangerous = []
        for p in game_state.players:
            if p.id == my_id or not p.alive:
                continue
            if len(p.cards) >= 4:
                dangerous.append(p.id)
        return dangerous


# Global card memory per game (reset on new game)
_card_memories: Dict[str, CardMemory] = {}


def get_card_memory(game_id: str) -> CardMemory:
    """Get or create card memory for a game."""
    if game_id not in _card_memories:
        _card_memories[game_id] = CardMemory()
    return _card_memories[game_id]


def reset_card_memory(game_id: str):
    """Reset card memory when a new game starts."""
    _card_memories.pop(game_id, None)


# --- RISK ASSESSMENT ---

def _threat_score(state: GameState, pid: int, territory: str) -> float:
    """Calculate how threatened a territory is (higher = more danger)."""
    ts = state.territories[territory]
    if ts.owner != pid:
        return 0.0

    threat = 0.0
    for n in get_neighbors(territory):
        ns = state.territories[n]
        if ns.owner != pid:
            # Enemy has more troops = more threat
            ratio = ns.troops / max(1, ts.troops)
            threat += max(0, ratio - 0.5)
            # Extra threat if enemy is strong nearby
            if ns.troops >= 5:
                threat += 1.0
    return threat


def _territory_strategic_value(state: GameState, pid: int, territory: str) -> float:
    """How strategically valuable is this territory to defend."""
    value = 0.0

    # Continent completion value
    for continent, territories in CONTINENTS.items():
        if territory not in territories:
            continue
        owned = sum(1 for t in territories if state.territories[t].owner == pid)
        total = len(territories)
        if owned == total:
            # We OWN this continent — critical to defend
            value += CONTINENT_BONUSES[continent] * 3
        elif owned >= total - 1:
            # Almost complete — high value
            value += CONTINENT_BONUSES[continent] * 2

    # Chokepoint value: territory connecting two clusters of our territories
    my_neighbors = sum(1 for n in get_neighbors(territory) if state.territories[n].owner == pid)
    enemy_neighbors = sum(1 for n in get_neighbors(territory) if state.territories[n].owner != pid)
    if my_neighbors >= 2 and enemy_neighbors >= 1:
        value += my_neighbors * 0.5

    return value


def _vulnerability_map(state: GameState, pid: int) -> Dict[str, float]:
    """Map of territory -> vulnerability score for all owned territories."""
    vuln = {}
    for t, ts in state.territories.items():
        if ts.owner == pid:
            threat = _threat_score(state, pid, t)
            strategic = _territory_strategic_value(state, pid, t)
            vuln[t] = threat * (1 + strategic)
    return vuln


# --- CONTINENT DEFENSE ---

def _owned_continents(state: GameState, pid: int) -> List[str]:
    """Return list of continents fully owned by player."""
    owned = []
    for continent, territories in CONTINENTS.items():
        if all(state.territories[t].owner == pid for t in territories):
            owned.append(continent)
    return owned


def _continent_border_territories(state: GameState, pid: int, continent: str) -> List[str]:
    """Return territories in a continent that border enemy territories."""
    borders = []
    for t in CONTINENTS[continent]:
        if any(state.territories[n].owner != pid for n in get_neighbors(t) if n in state.territories):
            borders.append(t)
    return borders


# --- SMART CARD TRADING ---

def _best_trade(cards: List[Card], state: GameState, pid: int) -> Optional[List[int]]:
    """Pick the best card set to trade, preferring territory bonus."""
    from .cards import find_valid_sets
    valid_sets = find_valid_sets(cards)
    if not valid_sets:
        return None

    best_indices = None
    best_score = -1

    for indices in valid_sets:
        selected = [cards[i] for i in indices]
        bonus = calculate_trade_bonus(selected)
        # Add territory bonus value
        territory_bonus = sum(
            2 for c in selected
            if c.territory and state.territories.get(c.territory, None)
            and state.territories[c.territory].owner == pid
        )
        score = bonus + territory_bonus
        if score > best_score:
            best_score = score
            best_indices = list(indices)

    return best_indices


# --- DIFFICULTY & PERSONALITY CONFIG ---

DIFFICULTY = {
    "easy": {
        "attack_ratio": 2.5, "max_attacks": 5, "reinforce_random": 0.5,
        "fortify_chance": 0.3, "continent_aware": False, "smart_cards": False,
        "risk_aware": False,
    },
    "medium": {
        "attack_ratio": 1.5, "max_attacks": 15, "reinforce_random": 0.2,
        "fortify_chance": 0.7, "continent_aware": False, "smart_cards": True,
        "risk_aware": False,
    },
    "hard": {
        "attack_ratio": 1.2, "max_attacks": 30, "reinforce_random": 0.0,
        "fortify_chance": 1.0, "continent_aware": True, "smart_cards": True,
        "risk_aware": True,
    },
}

PERSONALITIES = {
    "aggressive": {"attack_ratio_mod": -0.3, "max_attacks_mod": 10, "fortify_chance_mod": -0.2},
    "defensive": {"attack_ratio_mod": 0.5, "max_attacks_mod": -5, "fortify_chance_mod": 0.3},
    "expansionist": {"attack_ratio_mod": 0.0, "max_attacks_mod": 5, "fortify_chance_mod": 0.0, "continent_aware": True},
}

TRASH_TALK = {
    "aggressive": [
        "Preparati a perdere tutto! 💀",
        "Non c'è pietà in guerra!",
        "Il tuo esercito è patetico!",
        "Arrendersi è un'opzione... per te!",
        "Sto arrivando con tutto! ⚔️",
    ],
    "defensive": [
        "Provaci pure, le mie difese sono impenetrabili 🛡️",
        "Attacca se vuoi, ma non passerai!",
        "Pazienza... il momento giusto arriverà",
        "Costruisco, aspetto, vinco.",
        "Le mura reggono sempre 🏰",
    ],
    "expansionist": [
        "Un continente alla volta... 🌍",
        "Quasi ci sono... manca poco!",
        "La strategia batte la forza bruta",
        "Ogni territorio conta nel piano",
        "Il mondo sarà mio, pezzo per pezzo 🗺️",
    ],
}


def get_ai_personality(player_name: str) -> str:
    """Assign personality based on player name hash (deterministic)."""
    personalities = list(PERSONALITIES.keys())
    return personalities[hash(player_name) % len(personalities)]


def get_trash_talk(personality: str) -> str:
    """Get a random trash talk message for the personality."""
    return random.choice(TRASH_TALK.get(personality, TRASH_TALK["aggressive"]))


def _get_cfg(state: GameState, pid: int, difficulty: str) -> dict:
    """Build effective config with personality modifiers applied."""
    cfg = DIFFICULTY.get(difficulty, DIFFICULTY["medium"]).copy()
    player = next(p for p in state.players if p.id == pid)
    personality = get_ai_personality(player.name)
    mods = PERSONALITIES.get(personality, {})
    cfg["attack_ratio"] = max(1.0, cfg["attack_ratio"] + mods.get("attack_ratio_mod", 0))
    cfg["max_attacks"] = max(3, cfg["max_attacks"] + mods.get("max_attacks_mod", 0))
    cfg["fortify_chance"] = min(1.0, max(0, cfg["fortify_chance"] + mods.get("fortify_chance_mod", 0)))
    if mods.get("continent_aware"):
        cfg["continent_aware"] = True
    return cfg


# --- MAIN AI LOGIC ---

def ai_play_turn(game_state: GameState, engine, difficulty: str = "medium") -> List[dict]:
    """Execute a full AI turn with given difficulty."""
    player = game_state.players[game_state.current_player]
    pid = player.id
    cfg = _get_cfg(game_state, pid, difficulty)
    logs = []
    memory = get_card_memory(game_state.id)

    # --- SETUP PHASE ---
    if game_state.phase == GamePhase.SETUP:
        remaining = game_state.setup_troops_remaining.get(pid, 0)
        placed = 0
        while remaining > 0 and placed < 3 and game_state.phase == GamePhase.SETUP and game_state.players[game_state.current_player].id == pid:
            territory = _pick_setup_territory(game_state, pid, cfg)
            engine.place_setup_troops(pid, territory, 1)
            logs.append({"action": "setup", "territory": territory})
            remaining = game_state.setup_troops_remaining.get(pid, 0)
            placed += 1
        return logs

    # --- REINFORCE ---
    if game_state.phase == GamePhase.REINFORCE:
        # Smart card trading
        if len(player.cards) >= 3:
            if cfg["smart_cards"]:
                indices = _best_trade(player.cards, game_state, pid)
            else:
                indices = _find_valid_trade(player.cards)
            if indices is not None:
                try:
                    engine.trade_cards(pid, indices)
                    memory.record_trade(pid, game_state.turn_number)
                    logs.append({"action": "trade_cards"})
                except ValueError:
                    pass

        while player.troops_to_place > 0:
            territory = _pick_reinforce_territory(game_state, pid, cfg)
            troops = min(player.troops_to_place, 3)
            engine.place_troops(pid, territory, troops)
            logs.append({"action": "reinforce", "territory": territory, "troops": troops})

    # --- ATTACK ---
    attacks_done = 0
    trash_talked = False
    while game_state.phase == GamePhase.ATTACK and attacks_done < cfg["max_attacks"]:
        attack = _pick_attack(game_state, pid, cfg, memory)
        if not attack:
            break
        from_t, to_t, dice = attack
        try:
            result = engine.attack(pid, from_t, to_t, dice)
            attacks_done += 1
            log_entry = {
                "action": "attack", "from": from_t, "to": to_t,
                "dice": result.attacker_dice, "def_dice": result.defender_dice,
            }
            if not trash_talked and random.random() < 0.6:
                log_entry["trash_talk"] = get_trash_talk(get_ai_personality(player.name))
                trash_talked = True
            logs.append(log_entry)
            if game_state.phase == GamePhase.GAME_OVER:
                break
        except ValueError:
            break

    if game_state.phase == GamePhase.ATTACK:
        engine.end_attack_phase(pid)
        logs.append({"action": "end_attack"})

    # --- FORTIFY ---
    if game_state.phase == GamePhase.FORTIFY:
        if random.random() < cfg["fortify_chance"]:
            move = _pick_fortify(game_state, pid, cfg)
            if move:
                from_t, to_t, troops = move
                try:
                    engine.fortify(pid, from_t, to_t, troops)
                    logs.append({"action": "fortify", "from": from_t, "to": to_t, "troops": troops})
                    return logs
                except ValueError:
                    pass
        engine.end_turn(pid)
        logs.append({"action": "end_turn"})

    return logs


def _find_valid_trade(cards) -> Optional[List[int]]:
    """Find first valid 3-card set indices in a hand."""
    for i in range(len(cards)):
        for j in range(i + 1, len(cards)):
            for k in range(j + 1, len(cards)):
                if is_valid_set([cards[i], cards[j], cards[k]]):
                    return [i, j, k]
    return None


def _pick_setup_territory(state: GameState, pid: int, cfg: dict) -> str:
    owned = [t for t, s in state.territories.items() if s.owner == pid]
    if random.random() < cfg["reinforce_random"]:
        return random.choice(owned)
    border = [t for t in owned if any(
        state.territories[n].owner != pid for n in get_neighbors(t)
    )]
    return random.choice(border) if border else random.choice(owned)


def _pick_reinforce_territory(state: GameState, pid: int, cfg: dict) -> str:
    owned = [t for t, s in state.territories.items() if s.owner == pid]

    if random.random() < cfg["reinforce_random"]:
        return random.choice(owned)

    # PRIORITY 1: Defend owned continents (risk-aware)
    if cfg.get("risk_aware"):
        my_continents = _owned_continents(state, pid)
        if my_continents:
            # Find most threatened continent border
            worst_border = None
            worst_threat = 0
            for cont in my_continents:
                for t in _continent_border_territories(state, pid, cont):
                    threat = _threat_score(state, pid, t)
                    weighted = threat * CONTINENT_BONUSES[cont]
                    if weighted > worst_threat:
                        worst_threat = weighted
                        worst_border = t
            if worst_border and worst_threat > 2.0:
                return worst_border

    # PRIORITY 2: Near-complete continents
    if cfg["continent_aware"]:
        best = _continent_priority(state, pid)
        if best:
            return best

    # PRIORITY 3: Risk-aware — reinforce most vulnerable valuable territory
    if cfg.get("risk_aware"):
        vuln = _vulnerability_map(state, pid)
        if vuln:
            most_vulnerable = max(vuln, key=vuln.get)
            if vuln[most_vulnerable] > 3.0:
                return most_vulnerable

    # PRIORITY 4: Best attack opportunity
    border = [(t, state.territories[t].troops) for t in owned
              if any(state.territories[n].owner != pid for n in get_neighbors(t))]
    if not border:
        return random.choice(owned)

    best = None
    best_score = -999
    for t, troops in border:
        enemy_neighbors = [n for n in get_neighbors(t) if state.territories[n].owner != pid]
        if not enemy_neighbors:
            continue
        weakest_enemy = min(state.territories[n].troops for n in enemy_neighbors)
        attack_ratio_after = (troops + 3) / max(1, weakest_enemy)
        border_bonus = len(enemy_neighbors) * 0.3
        cont_bonus = sum(_continent_attack_bonus(state, pid, n) for n in enemy_neighbors)
        score = attack_ratio_after + border_bonus + cont_bonus
        if score > best_score:
            best_score = score
            best = t
    return best or border[0][0]


def _pick_attack(state: GameState, pid: int, cfg: dict, memory: CardMemory = None) -> Optional[Tuple[str, str, int]]:
    candidates = []
    min_ratio = cfg["attack_ratio"]

    # Risk-aware: be more cautious if opponents have many cards (incoming bonus troops)
    caution_modifier = 0.0
    if cfg.get("risk_aware") and memory:
        dangerous_opponents = memory.opponent_near_trade(state, pid)
        if dangerous_opponents:
            caution_modifier = 0.2  # Slightly more conservative

    for t, s in state.territories.items():
        if s.owner != pid or s.troops < 2:
            continue

        # Risk-aware: don't attack FROM a territory that's critical for continent defense
        if cfg.get("risk_aware"):
            my_continents = _owned_continents(state, pid)
            is_continent_border = False
            for cont in my_continents:
                if t in _continent_border_territories(state, pid, cont):
                    is_continent_border = True
                    break
            # Only attack from continent border if we have plenty of troops
            if is_continent_border and s.troops < 4:
                continue

        for n in get_neighbors(t):
            ns = state.territories[n]
            if ns.owner == pid:
                continue
            ratio = s.troops / max(1, ns.troops)
            effective_min = min_ratio + caution_modifier
            if ratio >= effective_min:
                dice = max_attacker_dice(s.troops)
                score = ratio

                # Continent completion bonus
                if cfg["continent_aware"]:
                    score += _continent_attack_bonus(state, pid, n) * 2

                # Weak isolated target bonus
                defender_support = sum(1 for nn in get_neighbors(n)
                                       if state.territories[nn].owner == ns.owner and nn != t)
                score += max(0, 3 - defender_support)

                # Strong position bonus
                if s.troops >= 6:
                    score += 1.5

                # Risk-aware: bonus for attacking players with many cards (eliminate them)
                if cfg.get("risk_aware") and memory:
                    if ns.owner in memory.opponent_near_trade(state, pid):
                        # Prioritize attacking players about to trade
                        enemy_territories = sum(1 for _, ts in state.territories.items() if ts.owner == ns.owner)
                        if enemy_territories <= 3:
                            score += 5.0  # Big bonus: might eliminate and steal cards

                candidates.append((t, n, dice, score))

    if not candidates:
        return None

    if cfg["reinforce_random"] > 0 and random.random() < cfg["reinforce_random"]:
        choice = random.choice(candidates)
    else:
        candidates.sort(key=lambda x: -x[3])
        choice = candidates[0]

    return choice[0], choice[1], choice[2]


def _pick_fortify(state: GameState, pid: int, cfg: dict) -> Optional[Tuple[str, str, int]]:
    owned = [t for t, s in state.territories.items() if s.owner == pid]

    # Risk-aware: fortify toward most threatened continent border
    if cfg.get("risk_aware"):
        my_continents = _owned_continents(state, pid)
        if my_continents:
            # Find weakest continent border
            worst_border = None
            worst_threat = 0
            for cont in my_continents:
                for t in _continent_border_territories(state, pid, cont):
                    threat = _threat_score(state, pid, t)
                    if threat > worst_threat:
                        worst_threat = threat
                        worst_border = t

            if worst_border and worst_threat > 1.5:
                # Find interior territory with most troops to move from
                interior = [t for t in owned
                            if state.territories[t].troops > 1
                            and all(state.territories[n].owner == pid
                                    for n in get_neighbors(t) if n in state.territories)]
                if interior:
                    source = max(interior, key=lambda x: state.territories[x].troops)
                    troops = state.territories[source].troops - 1
                    if troops > 0:
                        return source, worst_border, troops

    # Default: move from interior to border
    interior = [t for t in owned
                if state.territories[t].troops > 1
                and all(state.territories[n].owner == pid
                        for n in get_neighbors(t) if n in state.territories)]
    if not interior:
        return None

    for t in sorted(interior, key=lambda x: -state.territories[x].troops):
        for n in get_neighbors(t):
            if n not in state.territories or state.territories[n].owner != pid:
                continue
            if any(state.territories[nn].owner != pid for nn in get_neighbors(n) if nn in state.territories):
                troops = state.territories[t].troops - 1
                if troops > 0:
                    return t, n, troops
    return None


def _continent_priority(state: GameState, pid: int) -> Optional[str]:
    """Find a border territory in a near-complete continent to reinforce."""
    best_territory = None
    best_missing = 99

    for continent, territories in CONTINENTS.items():
        owned_in_cont = [t for t in territories if state.territories[t].owner == pid]
        missing = len(territories) - len(owned_in_cont)
        if 0 < missing <= 2 and missing < best_missing:
            missing_territories = [t for t in territories if state.territories[t].owner != pid]
            for mt in missing_territories:
                for n in get_neighbors(mt):
                    if n in state.territories and state.territories[n].owner == pid:
                        best_territory = n
                        best_missing = missing
                        break
    return best_territory


def _continent_attack_bonus(state: GameState, pid: int, target: str) -> float:
    """Bonus score for attacking a territory that completes a continent."""
    for continent, territories in CONTINENTS.items():
        if target not in territories:
            continue
        owned = sum(1 for t in territories if state.territories[t].owner == pid)
        total = len(territories)
        if owned >= total - 2:
            return 5.0
    return 0.0


# --- STEP-BASED AI (for animated turns) ---

def ai_play_step(game_state: GameState, engine, difficulty: str = "medium") -> Optional[dict]:
    """Execute ONE AI action. Returns log entry or None if nothing to do."""
    player = game_state.players[game_state.current_player]
    pid = player.id
    cfg = _get_cfg(game_state, pid, difficulty)
    memory = get_card_memory(game_state.id)

    if game_state.phase == GamePhase.SETUP:
        remaining = game_state.setup_troops_remaining.get(pid, 0)
        if remaining > 0:
            territory = _pick_setup_territory(game_state, pid, cfg)
            engine.place_setup_troops(pid, territory, 1)
            return {"action": "setup", "territory": territory}
        return None

    if game_state.phase == GamePhase.REINFORCE:
        if len(player.cards) >= 3:
            if cfg["smart_cards"]:
                indices = _best_trade(player.cards, game_state, pid)
            else:
                indices = _find_valid_trade(player.cards)
            if indices is not None:
                try:
                    engine.trade_cards(pid, indices)
                    memory.record_trade(pid, game_state.turn_number)
                    return {"action": "trade_cards"}
                except ValueError:
                    pass
        if player.troops_to_place > 0:
            territory = _pick_reinforce_territory(game_state, pid, cfg)
            troops = min(player.troops_to_place, 3)
            engine.place_troops(pid, territory, troops)
            return {"action": "reinforce", "territory": territory, "troops": troops}
        return None

    if game_state.phase == GamePhase.ATTACK:
        if not hasattr(engine, '_ai_attacks_this_turn'):
            engine._ai_attacks_this_turn = 0
        if engine._ai_attacks_this_turn >= cfg["max_attacks"]:
            engine._ai_attacks_this_turn = 0
            engine.end_attack_phase(pid)
            return {"action": "end_attack"}

        attack = _pick_attack(game_state, pid, cfg, memory)
        if not attack:
            engine._ai_attacks_this_turn = 0
            engine.end_attack_phase(pid)
            return {"action": "end_attack"}

        from_t, to_t, dice = attack
        try:
            result = engine.attack(pid, from_t, to_t, dice)
            engine._ai_attacks_this_turn += 1
            entry = {"action": "attack", "from": from_t, "to": to_t,
                     "dice": result.attacker_dice, "def_dice": result.defender_dice,
                     "att_loss": result.attacker_losses, "def_loss": result.defender_losses}
            if not hasattr(engine, '_ai_trash_talked') or not engine._ai_trash_talked:
                if random.random() < 0.5:
                    entry["trash_talk"] = get_trash_talk(get_ai_personality(player.name))
                    engine._ai_trash_talked = True
            return entry
        except ValueError:
            engine._ai_attacks_this_turn = 0
            engine.end_attack_phase(pid)
            return {"action": "end_attack"}

    if game_state.phase == GamePhase.FORTIFY:
        if random.random() < cfg["fortify_chance"]:
            move = _pick_fortify(game_state, pid, cfg)
            if move:
                from_t, to_t, troops = move
                try:
                    engine.fortify(pid, from_t, to_t, troops)
                    return {"action": "fortify", "from": from_t, "to": to_t, "troops": troops}
                except ValueError:
                    pass
        engine._ai_attacks_this_turn = 0
        engine._ai_trash_talked = False
        engine.end_turn(pid)
        return {"action": "end_turn"}

    return None


def ai_pick_next_attack(game_state: GameState, engine, difficulty: str = "medium"):
    """Pick next attack without executing it. Returns (from, to, dice) or None."""
    player = game_state.players[game_state.current_player]
    pid = player.id
    cfg = _get_cfg(game_state, pid, difficulty)
    memory = get_card_memory(game_state.id)

    if not hasattr(engine, '_ai_attacks_this_turn'):
        engine._ai_attacks_this_turn = 0
    if engine._ai_attacks_this_turn >= cfg.get("max_attacks", 15):
        return None

    return _pick_attack(game_state, pid, cfg, memory)
