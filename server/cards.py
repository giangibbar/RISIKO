"""Risiko card system — territory cards and set trading for bonus troops."""

import random
from typing import List, Optional, Tuple

from .models import Card, CardSymbol
from .map_data import get_all_territories


def create_deck() -> List[Card]:
    """Create and shuffle a full deck of 44 cards (42 territory + 2 wild)."""
    territories = get_all_territories()
    symbols = [CardSymbol.INFANTRY, CardSymbol.CAVALRY, CardSymbol.ARTILLERY]
    cards = [
        Card(territory=t, symbol=symbols[i % 3])
        for i, t in enumerate(territories)
    ]
    cards.append(Card(territory=None, symbol=CardSymbol.WILD))
    cards.append(Card(territory=None, symbol=CardSymbol.WILD))
    random.shuffle(cards)
    return cards


def is_valid_set(cards: List[Card]) -> bool:
    """
    Check if 3 cards form a valid tris for trading.

    Valid sets (Italian Risiko rules):
    - 3 cannoni (artillery): 4 armies
    - 3 fanti (infantry): 6 armies
    - 3 cavalieri (cavalry): 8 armies
    - 1 of each (fante + cannone + cavaliere): 10 armies
    - 1 jolly + 2 matching cards: 12 armies
    """
    if len(cards) != 3:
        return False

    wilds = sum(1 for c in cards if c.symbol == CardSymbol.WILD)

    if wilds >= 1:
        # Jolly + 2 cards of same symbol
        non_wild = [c for c in cards if c.symbol != CardSymbol.WILD]
        if len(non_wild) == 2 and non_wild[0].symbol == non_wild[1].symbol:
            return True
        # Jolly + any 2 is also valid (jolly acts as any)
        return True

    symbols = [c.symbol for c in cards]
    # All same
    if len(set(symbols)) == 1:
        return True
    # All different
    if len(set(symbols)) == 3:
        return True

    return False


def calculate_trade_bonus(cards: List[Card]) -> int:
    """
    Calculate troops received for trading a card set.

    Official Italian Risiko values:
    - 3 cannoni (artillery): 4
    - 3 fanti (infantry): 6
    - 3 cavalieri (cavalry): 8
    - 1 of each: 10
    - jolly + 2 same: 12
    """
    wilds = sum(1 for c in cards if c.symbol == CardSymbol.WILD)

    if wilds >= 1:
        return 12

    symbols = [c.symbol for c in cards]
    if len(set(symbols)) == 3:
        # One of each
        return 10
    # All same
    if symbols[0] == CardSymbol.ARTILLERY:
        return 4
    elif symbols[0] == CardSymbol.INFANTRY:
        return 6
    elif symbols[0] == CardSymbol.CAVALRY:
        return 8

    return 4  # Fallback


def find_valid_sets(cards: List[Card]) -> List[Tuple[int, int, int]]:
    """Find all valid 3-card combinations in a hand. Returns index tuples."""
    valid = []
    for i in range(len(cards)):
        for j in range(i + 1, len(cards)):
            for k in range(j + 1, len(cards)):
                if is_valid_set([cards[i], cards[j], cards[k]]):
                    valid.append((i, j, k))
    return valid
