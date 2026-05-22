"""Tournament mode — best of N series with local ELO ranking."""

import json
import os
import time
import uuid
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

# ELO constants
DEFAULT_ELO = 1000
K_FACTOR = 32
ELO_FILE = "elo_rankings.json"


class TournamentPlayer(BaseModel):
    """Player in a tournament."""
    name: str
    color: str
    is_ai: bool = False
    ai_difficulty: str = "medium"
    wins: int = 0


class TournamentState(BaseModel):
    """State of a tournament series."""
    id: str
    players: List[TournamentPlayer]
    best_of: int = 3
    current_match: int = 0  # 0-indexed
    match_results: List[Dict] = Field(default_factory=list)  # [{winner_name, turns, date}]
    winner: Optional[str] = None
    started_at: str = ""
    current_game_id: Optional[str] = None


# In-memory tournament storage
tournaments: Dict[str, TournamentState] = {}


def create_tournament(player_names: List[str], player_colors: List[str],
                      ai_players: List[bool], ai_difficulty: str = "medium",
                      best_of: int = 3) -> TournamentState:
    """Create a new tournament series."""
    players = [
        TournamentPlayer(name=n, color=c, is_ai=ai, ai_difficulty=ai_difficulty)
        for n, c, ai in zip(player_names, player_colors, ai_players)
    ]
    tournament = TournamentState(
        id=str(uuid.uuid4())[:8],
        players=players,
        best_of=best_of,
        started_at=time.strftime("%Y-%m-%d %H:%M"),
    )
    tournaments[tournament.id] = tournament
    return tournament


def record_match_result(tournament_id: str, winner_name: str, turns: int) -> TournamentState:
    """Record a match result and check if tournament is over."""
    t = tournaments[tournament_id]
    t.match_results.append({
        "winner_name": winner_name,
        "turns": turns,
        "date": time.strftime("%Y-%m-%d %H:%M"),
    })
    t.current_match += 1

    # Update wins
    for p in t.players:
        if p.name == winner_name:
            p.wins += 1
            break

    # Check if someone won the series
    wins_needed = (t.best_of // 2) + 1
    for p in t.players:
        if p.wins >= wins_needed:
            t.winner = p.name
            # Update ELO
            _update_elo_after_tournament(t)
            break

    return t


def get_tournament(tournament_id: str) -> Optional[TournamentState]:
    """Get tournament state."""
    return tournaments.get(tournament_id)


# --- ELO RANKING ---

def _load_elo() -> Dict[str, int]:
    """Load ELO rankings from file."""
    if os.path.exists(ELO_FILE):
        with open(ELO_FILE, "r") as f:
            return json.load(f)
    return {}


def _save_elo(rankings: Dict[str, int]):
    """Save ELO rankings to file."""
    with open(ELO_FILE, "w") as f:
        json.dump(rankings, f, indent=2)


def get_elo_rankings() -> List[Dict]:
    """Get all ELO rankings sorted by rating."""
    rankings = _load_elo()
    return sorted(
        [{"name": k, "elo": v} for k, v in rankings.items()],
        key=lambda x: -x["elo"]
    )


def _expected_score(rating_a: float, rating_b: float) -> float:
    """Calculate expected score for player A against player B."""
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400))


def _update_elo_after_tournament(tournament: TournamentState):
    """Update ELO ratings after a tournament ends."""
    rankings = _load_elo()
    winner_name = tournament.winner
    if not winner_name:
        return

    # Ensure all players have a rating
    for p in tournament.players:
        if p.name not in rankings:
            rankings[p.name] = DEFAULT_ELO

    # Winner gains ELO from each loser
    for p in tournament.players:
        if p.name == winner_name:
            continue
        winner_elo = rankings[winner_name]
        loser_elo = rankings[p.name]
        expected_w = _expected_score(winner_elo, loser_elo)
        expected_l = _expected_score(loser_elo, winner_elo)
        rankings[winner_name] = round(winner_elo + K_FACTOR * (1 - expected_w))
        rankings[p.name] = round(loser_elo + K_FACTOR * (0 - expected_l))

    _save_elo(rankings)
