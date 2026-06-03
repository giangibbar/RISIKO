"""Pydantic models for Risiko game state."""

from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class GamePhase(str, Enum):
    """Phases of a player's turn."""
    SETUP = "setup"                # Initial troop placement
    REINFORCE = "reinforce"        # Place bonus troops
    ATTACK = "attack"              # Attack adjacent territories
    FORTIFY = "fortify"            # Move troops between owned territories
    GAME_OVER = "game_over"


class CardSymbol(str, Enum):
    """Territory card symbols."""
    INFANTRY = "infantry"
    CAVALRY = "cavalry"
    ARTILLERY = "artillery"
    WILD = "wild"


class Card(BaseModel):
    """A territory card."""
    territory: Optional[str] = None  # None for wild cards
    symbol: CardSymbol


class Player(BaseModel):
    """Player state."""
    id: int
    name: str
    color: str
    is_ai: bool = False
    ai_difficulty: str = "medium"  # easy, medium, hard
    objective: str = ""  # Secret objective text
    eliminated_by: int | None = None  # Player ID who eliminated this player
    territories: List[str] = Field(default_factory=list)
    cards: List[Card] = Field(default_factory=list)
    troops_to_place: int = 0
    alive: bool = True
    conquered_this_turn: bool = False  # Earned a card this turn?


class TerritoryState(BaseModel):
    """State of a single territory."""
    owner: int  # Player ID
    troops: int = 1


class CombatResult(BaseModel):
    """Result of a single combat round."""
    attacker_dice: List[int]
    defender_dice: List[int]
    attacker_losses: int
    defender_losses: int


class GameState(BaseModel):
    """Complete game state."""
    id: str
    players: List[Player]
    territories: Dict[str, TerritoryState] = Field(default_factory=dict)
    current_player: int = 0  # Index into players list
    phase: GamePhase = GamePhase.SETUP
    turn_number: int = 0
    card_deck: List[Card] = Field(default_factory=list)
    card_sets_traded: int = 0  # How many sets have been traded globally
    winner: Optional[int] = None
    setup_troops_remaining: Dict[int, int] = Field(default_factory=dict)


# --- API Request/Response models ---

class CreateGameRequest(BaseModel):
    """Request to create a new game."""
    player_names: List[str]
    player_colors: List[str]
    ai_players: List[bool] = Field(default_factory=list)
    ai_difficulty: str = "medium"  # easy, medium, hard — applies to all AI


class PlaceTroopsRequest(BaseModel):
    """Place troops on a territory."""
    territory: str
    troops: int = 1


class AttackRequest(BaseModel):
    """Attack from one territory to another."""
    from_territory: str
    to_territory: str
    num_dice: int  # 1-3


class FortifyRequest(BaseModel):
    """Move troops between owned adjacent territories."""
    from_territory: str
    to_territory: str
    troops: int


class TradeCardsRequest(BaseModel):
    """Trade a set of 3 cards for bonus troops."""
    card_indices: List[int]  # Indices into player's card list
