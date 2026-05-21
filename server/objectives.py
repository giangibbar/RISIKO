"""Secret objectives for Risiko — all 14 official Italian objectives."""

import random
from typing import List


def _has_continents(player, territories, continent_ids: List[str]) -> bool:
    from .map_data import CONTINENTS
    for cid in continent_ids:
        for t in CONTINENTS[cid]:
            if territories[t].owner != player.id:
                return False
    return True


def _territories_with_min_troops(player, territories, count: int, min_troops: int) -> bool:
    return sum(1 for t in player.territories if territories[t].troops >= min_troops) >= count


def _player_eliminated(target_color: str, players) -> bool:
    for p in players:
        if p.color == target_color and not p.alive:
            return True
    return False


# All 14 official objectives
OBJECTIVES = [
    # 6 continent combinations
    {"text": "Conquistare l'Europa e l'Oceania",
     "check": lambda p, t, ps: _has_continents(p, t, ["europe", "oceania"])},
    {"text": "Conquistare l'Europa e il Sud America",
     "check": lambda p, t, ps: _has_continents(p, t, ["europe", "south_america"])},
    {"text": "Conquistare il Nord America e l'Africa",
     "check": lambda p, t, ps: _has_continents(p, t, ["north_america", "africa"])},
    {"text": "Conquistare il Nord America e l'Oceania",
     "check": lambda p, t, ps: _has_continents(p, t, ["north_america", "oceania"])},
    {"text": "Conquistare l'Asia e il Sud America",
     "check": lambda p, t, ps: _has_continents(p, t, ["asia", "south_america"])},
    {"text": "Conquistare l'Asia e l'Africa",
     "check": lambda p, t, ps: _has_continents(p, t, ["asia", "africa"])},
    # 2 territory count objectives
    {"text": "Conquistare almeno 24 territori",
     "check": lambda p, t, ps: len(p.territories) >= 24},
    {"text": "Conquistare 18 territori con almeno 2 armate ciascuno",
     "check": lambda p, t, ps: _territories_with_min_troops(p, t, 18, 2)},
    # 6 "destroy color" objectives
    {"text": "Distruggere l'armata ROSSA (se sei tu, conquista 24 territori)",
     "color_target": "#e63946",
     "check": lambda p, t, ps: _check_destroy(p, t, ps, "#e63946")},
    {"text": "Distruggere l'armata BLU (se sei tu, conquista 24 territori)",
     "color_target": "#2563eb",
     "check": lambda p, t, ps: _check_destroy(p, t, ps, "#2563eb")},
    {"text": "Distruggere l'armata VERDE (se sei tu, conquista 24 territori)",
     "color_target": "#2a9d8f",
     "check": lambda p, t, ps: _check_destroy(p, t, ps, "#2a9d8f")},
    {"text": "Distruggere l'armata GIALLA (se sei tu, conquista 24 territori)",
     "color_target": "#f4d35e",
     "check": lambda p, t, ps: _check_destroy(p, t, ps, "#f4d35e")},
    {"text": "Distruggere l'armata NERA (se sei tu, conquista 24 territori)",
     "color_target": "#222222",
     "check": lambda p, t, ps: _check_destroy(p, t, ps, "#222222")},
    {"text": "Distruggere l'armata VIOLA (se sei tu, conquista 24 territori)",
     "color_target": "#7b2d8b",
     "check": lambda p, t, ps: _check_destroy(p, t, ps, "#7b2d8b")},
]


def _check_destroy(player, territories, players, target_color: str) -> bool:
    """If target is yourself or not in game, fallback to 24 territories."""
    # Find target player
    target = None
    for p in players:
        if p.color == target_color and p.id != player.id:
            target = p
            break

    if target is None:
        # Target color is yourself or not in game — fallback to 24 territories
        return len(player.territories) >= 24

    return not target.alive


def assign_objectives(num_players: int, player_colors: List[str] = None) -> List[str]:
    """Assign random secret objectives. Avoids giving 'destroy X' to player X."""
    available = OBJECTIVES.copy()
    random.shuffle(available)
    assigned = []

    for i in range(num_players):
        color = player_colors[i] if player_colors else None
        # Pick an objective, skip if it targets yourself
        for obj in available:
            target = obj.get("color_target")
            if target and target == color:
                continue  # Don't give "destroy yourself"
            assigned.append(obj["text"])
            available.remove(obj)
            break
        else:
            # Fallback
            assigned.append("Conquistare almeno 24 territori")

    return assigned


def check_objective(player, territories, objective_text: str, players=None) -> bool:
    """Check if a player has completed their objective."""
    for obj in OBJECTIVES:
        if obj["text"] == objective_text:
            return obj["check"](player, territories, players or [])
    return False
