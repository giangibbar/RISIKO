"""AI player logic for Risiko — difficulty-based decision making."""

import random
from typing import List, Tuple

from .models import GameState, GamePhase
from .map_data import get_neighbors, CONTINENTS
from .combat import max_attacker_dice
from .cards import is_valid_set


def _find_valid_trade(cards) -> list | None:
    """Find first valid 3-card set indices in a hand."""
    for i in range(len(cards)):
        for j in range(i + 1, len(cards)):
            for k in range(j + 1, len(cards)):
                if is_valid_set([cards[i], cards[j], cards[k]]):
                    return [i, j, k]
    return None
from .combat import max_attacker_dice

# Difficulty settings
DIFFICULTY = {
    "easy": {
        "attack_ratio": 2.5, "max_attacks": 5, "reinforce_random": 0.5,
        "fortify_chance": 0.3, "continent_aware": False,
    },
    "medium": {
        "attack_ratio": 1.5, "max_attacks": 15, "reinforce_random": 0.2,
        "fortify_chance": 0.7, "continent_aware": False,
    },
    "hard": {
        "attack_ratio": 1.2, "max_attacks": 30, "reinforce_random": 0.0,
        "fortify_chance": 1.0, "continent_aware": True,
    },
}

# AI Personalities (applied on top of difficulty)
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
    messages = TRASH_TALK.get(personality, TRASH_TALK["aggressive"])
    return random.choice(messages)


def ai_play_turn(game_state: GameState, engine, difficulty: str = "medium") -> List[dict]:
    """Execute a full AI turn with given difficulty."""
    cfg = DIFFICULTY.get(difficulty, DIFFICULTY["medium"]).copy()
    logs = []
    player = game_state.players[game_state.current_player]
    pid = player.id

    # Apply personality modifiers
    personality = get_ai_personality(player.name)
    mods = PERSONALITIES.get(personality, {})
    cfg["attack_ratio"] = max(1.0, cfg["attack_ratio"] + mods.get("attack_ratio_mod", 0))
    cfg["max_attacks"] = max(3, cfg["max_attacks"] + mods.get("max_attacks_mod", 0))
    cfg["fortify_chance"] = min(1.0, max(0, cfg["fortify_chance"] + mods.get("fortify_chance_mod", 0)))
    if mods.get("continent_aware"):
        cfg["continent_aware"] = True

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
        if len(player.cards) >= 3:
            valid_set = _find_valid_trade(player.cards)
            if valid_set is not None:
                try:
                    engine.trade_cards(pid, valid_set)
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
        attack = _pick_attack(game_state, pid, cfg)
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
                log_entry["trash_talk"] = get_trash_talk(personality)
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

    # Prioritize near-complete continents
    if cfg["continent_aware"]:
        best_continent_territory = _continent_priority(state, pid)
        if best_continent_territory:
            return best_continent_territory

    border = [(t, state.territories[t].troops) for t in owned
              if any(state.territories[n].owner != pid for n in get_neighbors(t))]
    if not border:
        return random.choice(owned)

    # Smart: reinforce where we can create a strong attack opportunity
    best = None
    best_score = -999
    for t, troops in border:
        enemy_neighbors = [n for n in get_neighbors(t) if state.territories[n].owner != pid]
        if not enemy_neighbors:
            continue
        weakest_enemy = min(state.territories[n].troops for n in enemy_neighbors)
        # Prefer territories where adding troops creates attack advantage
        attack_ratio_after = (troops + 3) / max(1, weakest_enemy)
        # Bonus for strategic positions (many borders)
        border_bonus = len(enemy_neighbors) * 0.3
        # Bonus for continent completion
        cont_bonus = sum(_continent_attack_bonus(state, pid, n) for n in enemy_neighbors)
        score = attack_ratio_after + border_bonus + cont_bonus
        if score > best_score:
            best_score = score
            best = t
    return best or border[0][0]


def _pick_attack(state: GameState, pid: int, cfg: dict) -> Tuple[str, str, int] | None:
    candidates = []
    min_ratio = cfg["attack_ratio"]

    for t, s in state.territories.items():
        if s.owner != pid or s.troops < 2:
            continue
        for n in get_neighbors(t):
            ns = state.territories[n]
            if ns.owner == pid:
                continue
            ratio = s.troops / max(1, ns.troops)
            if ratio >= min_ratio:
                dice = max_attacker_dice(s.troops)
                score = ratio
                # Bonus: continent completion
                if cfg["continent_aware"]:
                    score += _continent_attack_bonus(state, pid, n) * 2
                # Bonus: attack weak isolated territories (fewer friendly neighbors for defender)
                defender_support = sum(1 for nn in get_neighbors(n) if state.territories[nn].owner == ns.owner and nn != t)
                score += max(0, 3 - defender_support)  # Less support = better target
                # Bonus: attack from strong position (more troops = safer)
                if s.troops >= 6:
                    score += 1.5
                candidates.append((t, n, dice, score))

    if not candidates:
        return None

    if cfg["reinforce_random"] > 0 and random.random() < cfg["reinforce_random"]:
        choice = random.choice(candidates)
    else:
        candidates.sort(key=lambda x: -x[3])
        choice = candidates[0]

    return choice[0], choice[1], choice[2]


def _pick_fortify(state: GameState, pid: int, cfg: dict) -> Tuple[str, str, int] | None:
    owned = [t for t, s in state.territories.items() if s.owner == pid]
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


def _continent_priority(state: GameState, pid: int) -> str | None:
    """Find a border territory in a near-complete continent to reinforce."""
    best_territory = None
    best_missing = 99

    for continent, territories in CONTINENTS.items():
        owned_in_cont = [t for t in territories if state.territories[t].owner == pid]
        missing = len(territories) - len(owned_in_cont)
        # If we own most of a continent (1-2 missing), prioritize it
        if 0 < missing <= 2 and missing < best_missing:
            # Find our territory adjacent to the missing ones
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
            return 5.0  # Big bonus for near-complete continent
    return 0.0


def ai_play_step(game_state: GameState, engine, difficulty: str = "medium") -> dict | None:
    """Execute ONE AI action. Returns log entry or None if nothing to do."""
    cfg = DIFFICULTY.get(difficulty, DIFFICULTY["medium"]).copy()
    player = game_state.players[game_state.current_player]
    pid = player.id

    personality = get_ai_personality(player.name)
    mods = PERSONALITIES.get(personality, {})
    cfg["attack_ratio"] = max(1.0, cfg["attack_ratio"] + mods.get("attack_ratio_mod", 0))
    cfg["max_attacks"] = max(3, cfg["max_attacks"] + mods.get("max_attacks_mod", 0))
    cfg["fortify_chance"] = min(1.0, max(0, cfg["fortify_chance"] + mods.get("fortify_chance_mod", 0)))
    if mods.get("continent_aware"):
        cfg["continent_aware"] = True

    if game_state.phase == GamePhase.SETUP:
        remaining = game_state.setup_troops_remaining.get(pid, 0)
        if remaining > 0:
            territory = _pick_setup_territory(game_state, pid, cfg)
            engine.place_setup_troops(pid, territory, 1)
            return {"action": "setup", "territory": territory}
        return None

    if game_state.phase == GamePhase.REINFORCE:
        if len(player.cards) >= 3:
            valid_set = _find_valid_trade(player.cards)
            if valid_set is not None:
                try:
                    engine.trade_cards(pid, valid_set)
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
        # Track attacks done (use a simple counter on the engine)
        if not hasattr(engine, '_ai_attacks_this_turn'):
            engine._ai_attacks_this_turn = 0
        if engine._ai_attacks_this_turn >= cfg["max_attacks"]:
            engine._ai_attacks_this_turn = 0
            engine.end_attack_phase(pid)
            return {"action": "end_attack"}

        attack = _pick_attack(game_state, pid, cfg)
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
                    entry["trash_talk"] = get_trash_talk(personality)
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
    cfg = DIFFICULTY.get(difficulty, DIFFICULTY["medium"]).copy()
    player = game_state.players[game_state.current_player]
    pid = player.id
    personality = get_ai_personality(player.name)
    mods = PERSONALITIES.get(personality, {})
    cfg["attack_ratio"] = max(1.0, cfg["attack_ratio"] + mods.get("attack_ratio_mod", 0))
    if mods.get("continent_aware"):
        cfg["continent_aware"] = True

    if not hasattr(engine, '_ai_attacks_this_turn'):
        engine._ai_attacks_this_turn = 0
    if engine._ai_attacks_this_turn >= cfg.get("max_attacks", 15):
        return None

    return _pick_attack(game_state, pid, cfg)
