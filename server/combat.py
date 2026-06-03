"""Risiko combat system — dice rolling and resolution."""

import random
from typing import List, Tuple

from .models import CombatResult


def roll_dice(num_dice: int) -> List[int]:
    """Roll n dice, return sorted descending."""
    return sorted([random.randint(1, 6) for _ in range(num_dice)], reverse=True)


def resolve_combat(attacker_dice: int, defender_dice: int) -> CombatResult:
    """
    Resolve one round of combat.

    Rules:
    - Attacker rolls 1-3 dice (must have at least n+1 troops on territory)
    - Defender rolls 1-2 dice (1 if only 1 troop, else can choose 1 or 2)
    - Compare highest dice: defender wins ties
    - If both rolled 2+, compare second highest too
    """
    att_rolls = roll_dice(attacker_dice)
    def_rolls = roll_dice(defender_dice)

    attacker_losses, defender_losses = compare_dice(att_rolls, def_rolls)

    return CombatResult(
        attacker_dice=att_rolls,
        defender_dice=def_rolls,
        attacker_losses=attacker_losses,
        defender_losses=defender_losses,
    )


def compare_dice(att_rolls: List[int], def_rolls: List[int]) -> Tuple[int, int]:
    """Compare dice pairs. Returns (attacker_losses, defender_losses)."""
    attacker_losses = 0
    defender_losses = 0
    pairs = min(len(att_rolls), len(def_rolls))

    for i in range(pairs):
        if att_rolls[i] > def_rolls[i]:
            defender_losses += 1
        else:
            attacker_losses += 1  # Defender wins ties

    return attacker_losses, defender_losses


def max_attacker_dice(troops_on_territory: int) -> int:
    """Max dice attacker can roll (must leave at least 1 troop behind)."""
    return min(3, troops_on_territory - 1)


def max_defender_dice(troops_on_territory: int) -> int:
    """Max dice defender can roll (up to 3 per Italian Risiko rules)."""
    return min(3, troops_on_territory)


def attack_probability(attacker_troops: int, defender_troops: int) -> float:
    """Estimate probability of attacker winning (Monte Carlo, 100 sims)."""
    wins = 0
    for _ in range(100):
        att, defe = attacker_troops, defender_troops
        while att > 1 and defe > 0:
            ad = min(3, att - 1)
            dd = min(3, defe)
            a_rolls = sorted([random.randint(1,6) for _ in range(ad)], reverse=True)
            d_rolls = sorted([random.randint(1,6) for _ in range(dd)], reverse=True)
            for i in range(min(ad, dd)):
                if a_rolls[i] > d_rolls[i]:
                    defe -= 1
                else:
                    att -= 1
        if defe <= 0:
            wins += 1
    return round(wins / 100 * 100)
