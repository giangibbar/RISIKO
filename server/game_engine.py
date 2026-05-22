"""Risiko game engine — full game logic."""

import random
import uuid
from typing import Dict, List, Optional, Tuple

from .models import (
    GameState, GamePhase, Player, TerritoryState,
    CombatResult, Card,
)
from .map_data import (
    get_all_territories, CONTINENTS, CONTINENT_BONUSES,
    are_adjacent, get_neighbors, get_player_continent_bonuses,
)
from .combat import resolve_combat, max_attacker_dice, max_defender_dice
from .cards import create_deck, is_valid_set, calculate_trade_bonus
from .objectives import assign_objectives, check_objective

# Initial troops by player count (classic Risiko rules)
INITIAL_TROOPS = {2: 40, 3: 35, 4: 30, 5: 25, 6: 20}


class GameEngine:
    """Manages a single Risiko game."""

    def __init__(self, game: GameState):
        self.game = game

    @classmethod
    def create_game(cls, player_names: List[str], player_colors: List[str], ai_players: List[bool] = None, ai_difficulty: str = "medium", map_variant: str = "classic") -> "GameEngine":
        """Create a new game with random territory assignment."""
        num_players = len(player_names)
        if not 2 <= num_players <= 6:
            raise ValueError("Need 2-6 players")
        if len(player_colors) != num_players:
            raise ValueError("Colors must match player count")
        if ai_players is None:
            ai_players = [False] * num_players

        players = [
            Player(id=i, name=name, color=color,
                   is_ai=ai_players[i] if i < len(ai_players) else False,
                   ai_difficulty=ai_difficulty)
            for i, (name, color) in enumerate(zip(player_names, player_colors))
        ]

        # Assign secret objectives
        objectives = assign_objectives(num_players, player_colors)
        for i, p in enumerate(players):
            p.objective = objectives[i]

        # Randomly distribute territories
        territories = get_all_territories()
        random.shuffle(territories)
        territory_states: Dict[str, TerritoryState] = {}

        for i, t in enumerate(territories):
            owner = i % num_players
            territory_states[t] = TerritoryState(owner=owner, troops=1)
            players[owner].territories.append(t)

        # Calculate setup troops remaining
        initial = INITIAL_TROOPS[num_players]
        setup_remaining = {}
        for p in players:
            setup_remaining[p.id] = initial - len(p.territories)

        game = GameState(
            id=str(uuid.uuid4())[:8],
            players=players,
            territories=territory_states,
            phase=GamePhase.SETUP,
            card_deck=create_deck(),
            setup_troops_remaining=setup_remaining,
        )

        engine = cls(game)
        if all(v <= 0 for v in setup_remaining.values()):
            engine._start_turn()
        return engine

    # --- SETUP PHASE ---

    def place_setup_troops(self, player_id: int, territory: str, troops: int = 1) -> str:
        """Place troops during setup phase. 1 at a time, turn passes after 3 placed."""
        self._assert_phase(GamePhase.SETUP)
        self._assert_current_player(player_id)

        remaining = self.game.setup_troops_remaining.get(player_id, 0)
        if remaining <= 0:
            raise ValueError("No troops left to place")
        if troops < 1:
            troops = 1
        troops = min(troops, remaining)
        if self.game.territories[territory].owner != player_id:
            raise ValueError("Can only place on own territories")

        self.game.territories[territory].troops += troops
        self.game.setup_troops_remaining[player_id] = remaining - troops

        # Track how many placed this round (stored transiently)
        if not hasattr(self, '_setup_placed_this_round'):
            self._setup_placed_this_round = 0
        self._setup_placed_this_round += troops

        # After 3 placed (or no more remaining), advance to next player
        new_remaining = self.game.setup_troops_remaining[player_id]
        if self._setup_placed_this_round >= 3 or new_remaining <= 0:
            self._setup_placed_this_round = 0
            self._advance_setup()

        return f"Placed {troops} on {territory}"

    def _advance_setup(self):
        """Move to next player in setup, or start game if all done."""
        # Find next player with troops to place
        num_players = len(self.game.players)
        for _ in range(num_players):
            self.game.current_player = (self.game.current_player + 1) % num_players
            pid = self.game.players[self.game.current_player].id
            if self.game.setup_troops_remaining.get(pid, 0) > 0:
                return

        # All placed — start the game
        self.game.current_player = 0
        self._start_turn()

    # --- TURN MANAGEMENT ---

    def _start_turn(self):
        """Begin a new turn: calculate and assign reinforcements."""
        self.game.phase = GamePhase.REINFORCE
        self.game.turn_number += 1
        self._reinforce_history = []
        player = self._current_player()
        player.conquered_this_turn = False

        # Calculate reinforcements
        num_territories = len(player.territories)
        base_troops = max(3, num_territories // 3)
        continent_bonus = get_player_continent_bonuses(set(player.territories))
        total = base_troops + continent_bonus
        player.troops_to_place = total

    def end_attack_phase(self, player_id: int) -> str:
        """Player chooses to stop attacking and move to fortify."""
        self._assert_phase(GamePhase.ATTACK)
        self._assert_current_player(player_id)
        self.game.phase = GamePhase.FORTIFY
        return "Moved to fortify phase"

    def end_turn(self, player_id: int) -> str:
        """End current player's turn (skip fortify or after fortify)."""
        self._assert_current_player(player_id)
        if self.game.phase not in (GamePhase.ATTACK, GamePhase.FORTIFY):
            raise ValueError(f"Cannot end turn during {self.game.phase}")

        # Award card if conquered at least one territory
        player = self._current_player()
        if player.conquered_this_turn and self.game.card_deck:
            card = self.game.card_deck.pop()
            player.cards.append(card)

        # Next alive player
        self._next_player()
        self._start_turn()
        return f"Turn passed to {self._current_player().name}"

    def _next_player(self):
        """Advance to next alive player."""
        num = len(self.game.players)
        for _ in range(num):
            self.game.current_player = (self.game.current_player + 1) % num
            if self.game.players[self.game.current_player].alive:
                return
        # Should not reach here if game isn't over

    # --- REINFORCE PHASE ---

    def place_troops(self, player_id: int, territory: str, troops: int) -> str:
        """Place reinforcement troops on owned territory."""
        self._assert_phase(GamePhase.REINFORCE)
        self._assert_current_player(player_id)
        player = self._current_player()

        # Must trade cards first if holding 5+
        if len(player.cards) >= 5:
            raise ValueError("Devi scambiare carte prima (hai 5+ carte)")

        if troops < 1 or troops > player.troops_to_place:
            raise ValueError(f"Must place 1-{player.troops_to_place} troops")
        if self.game.territories[territory].owner != player_id:
            raise ValueError("Can only reinforce own territories")

        self.game.territories[territory].troops += troops
        player.troops_to_place -= troops

        # Track for undo
        if not hasattr(self, '_reinforce_history'):
            self._reinforce_history = []
        self._reinforce_history.append((territory, troops))

        # Auto-advance to attack when all troops placed
        if player.troops_to_place <= 0:
            self.game.phase = GamePhase.ATTACK

        self._check_win(player_id)

        return f"Placed {troops} on {territory} ({player.troops_to_place} remaining)"

    def undo_reinforce(self, player_id: int) -> str:
        """Undo last reinforcement placement."""
        self._assert_phase(GamePhase.REINFORCE)
        self._assert_current_player(player_id)
        if not hasattr(self, '_reinforce_history') or not self._reinforce_history:
            raise ValueError("Nothing to undo")
        territory, troops = self._reinforce_history.pop()
        self.game.territories[territory].troops -= troops
        self._current_player().troops_to_place += troops
        return f"Undid {troops} from {territory}"

    def rapid_attack(self, player_id: int, from_t: str, to_t: str) -> List[CombatResult]:
        """Attack repeatedly until conquest or attacker has only 1 troop."""
        self._assert_phase(GamePhase.ATTACK)
        self._assert_current_player(player_id)
        results = []
        while (self.game.territories[from_t].troops > 1 and
               self.game.territories[to_t].owner != player_id and
               self.game.phase == GamePhase.ATTACK):
            dice = max_attacker_dice(self.game.territories[from_t].troops)
            result = self.attack(player_id, from_t, to_t, dice)
            results.append(result)
            if self.game.phase == GamePhase.GAME_OVER:
                break
        return results

    # --- TRADE CARDS ---

    def trade_cards(self, player_id: int, card_indices: List[int]) -> str:
        """Trade a set of 3 cards for bonus troops."""
        self._assert_phase(GamePhase.REINFORCE)
        self._assert_current_player(player_id)
        player = self._current_player()

        if len(card_indices) != 3:
            raise ValueError("Must trade exactly 3 cards")
        if any(i < 0 or i >= len(player.cards) for i in card_indices):
            raise ValueError("Invalid card index")

        selected = [player.cards[i] for i in card_indices]
        if not is_valid_set(selected):
            raise ValueError("Cards don't form a valid set")

        bonus = calculate_trade_bonus(selected)
        self.game.card_sets_traded += 1
        player.troops_to_place += bonus

        # Territory bonus: +2 for EACH traded card showing a territory you own
        for card in selected:
            if card.territory and self.game.territories[card.territory].owner == player_id:
                self.game.territories[card.territory].troops += 2

        # Remove cards (reverse order to preserve indices)
        for i in sorted(card_indices, reverse=True):
            player.cards.pop(i)

        return f"Traded cards for {bonus} bonus troops"

    # --- ATTACK PHASE ---

    def attack(self, player_id: int, from_t: str, to_t: str, num_dice: int) -> CombatResult:
        """Execute one attack round."""
        self._assert_phase(GamePhase.ATTACK)
        self._assert_current_player(player_id)

        # Validate
        if self.game.territories[from_t].owner != player_id:
            raise ValueError("Don't own attacking territory")
        if self.game.territories[to_t].owner == player_id:
            raise ValueError("Can't attack own territory")
        if not are_adjacent(from_t, to_t):
            raise ValueError("Territories not adjacent")

        att_troops = self.game.territories[from_t].troops
        max_dice = max_attacker_dice(att_troops)
        if num_dice < 1 or num_dice > max_dice:
            raise ValueError(f"Can roll 1-{max_dice} dice (have {att_troops} troops)")

        def_troops = self.game.territories[to_t].troops
        def_dice = max_defender_dice(def_troops)

        # Resolve combat
        result = resolve_combat(num_dice, def_dice)

        # Apply losses
        self.game.territories[from_t].troops -= result.attacker_losses
        self.game.territories[to_t].troops -= result.defender_losses

        # Track dice used for post-conquest minimum
        self._last_attack_dice = num_dice

        # Check conquest
        if self.game.territories[to_t].troops <= 0:
            self._conquer(player_id, from_t, to_t, num_dice)

        return result

    def _conquer(self, player_id: int, from_t: str, to_t: str, attacking_dice: int):
        """Handle territory conquest."""
        defender_id = self.game.territories[to_t].owner
        player = self._current_player()
        defender = self.game.players[defender_id]

        # Transfer ownership
        self.game.territories[to_t].owner = player_id
        self.game.territories[to_t].troops = attacking_dice  # Move attacking dice count
        self.game.territories[from_t].troops -= attacking_dice

        # Ensure at least 1 troop remains on source
        if self.game.territories[from_t].troops < 1:
            self.game.territories[from_t].troops = 1
            self.game.territories[to_t].troops = attacking_dice - 1 or 1

        player.territories.append(to_t)
        defender.territories.remove(to_t)
        player.conquered_this_turn = True

        # Check if defender eliminated
        if not defender.territories:
            defender.alive = False
            # Take their cards
            player.cards.extend(defender.cards)
            defender.cards.clear()

        # Check win condition
        self._check_win(player_id)

    def _check_win(self, player_id: int):
        """Check if player has won (elimination or objective)."""
        if self.game.phase == GamePhase.GAME_OVER:
            return
        player = self.game.players[player_id]
        alive_players = [p for p in self.game.players if p.alive]
        if len(alive_players) == 1:
            self.game.phase = GamePhase.GAME_OVER
            self.game.winner = player_id
        elif player.objective and check_objective(player, self.game.territories, player.objective, self.game.players):
            self.game.phase = GamePhase.GAME_OVER
            self.game.winner = player_id

    def move_after_conquest(self, player_id: int, from_t: str, to_t: str, troops: int) -> str:
        """Move additional troops into conquered territory."""
        self._assert_phase(GamePhase.ATTACK)
        self._assert_current_player(player_id)

        if self.game.territories[from_t].owner != player_id:
            raise ValueError("Don't own source territory")
        if self.game.territories[to_t].owner != player_id:
            raise ValueError("Don't own target territory")
        if not are_adjacent(from_t, to_t):
            raise ValueError("Territories not adjacent")
        if self.game.territories[from_t].troops - troops < 1:
            raise ValueError("Must leave at least 1 troop")

        self.game.territories[from_t].troops -= troops
        self.game.territories[to_t].troops += troops
        self._check_win(player_id)
        return f"Moved {troops} troops from {from_t} to {to_t}"

    # --- FORTIFY PHASE ---

    def fortify(self, player_id: int, from_t: str, to_t: str, troops: int) -> str:
        """Move troops between owned connected territories (one move per turn)."""
        self._assert_phase(GamePhase.FORTIFY)
        self._assert_current_player(player_id)

        if self.game.territories[from_t].owner != player_id:
            raise ValueError("Don't own source territory")
        if self.game.territories[to_t].owner != player_id:
            raise ValueError("Don't own target territory")
        if not self._are_connected(from_t, to_t, player_id):
            raise ValueError("Territories not connected through your territories")
        if troops < 1 or self.game.territories[from_t].troops - troops < 1:
            raise ValueError("Invalid troop count (must leave at least 1)")

        self.game.territories[from_t].troops -= troops
        self.game.territories[to_t].troops += troops

        self._check_win(player_id)
        if self.game.phase == GamePhase.GAME_OVER:
            return f"Moved {troops} from {from_t} to {to_t}"

        # Fortify ends the turn
        player = self._current_player()
        if player.conquered_this_turn and self.game.card_deck:
            card = self.game.card_deck.pop()
            player.cards.append(card)

        self._next_player()
        self._start_turn()
        return f"Fortified {to_t} with {troops} troops. Turn ended."

    # --- HELPERS ---

    def _current_player(self) -> Player:
        return self.game.players[self.game.current_player]

    def _assert_phase(self, phase: GamePhase):
        if self.game.phase != phase:
            raise ValueError(f"Wrong phase: expected {phase}, got {self.game.phase}")

    def _assert_current_player(self, player_id: int):
        if self._current_player().id != player_id:
            raise ValueError(f"Not your turn (current: {self._current_player().name})")

    def _are_connected(self, from_t: str, to_t: str, player_id: int) -> bool:
        """BFS: check if two territories are connected through player's territories."""
        visited = set()
        queue = [from_t]
        while queue:
            current = queue.pop(0)
            if current == to_t:
                return True
            if current in visited:
                continue
            visited.add(current)
            for neighbor in get_neighbors(current):
                if neighbor not in visited and self.game.territories[neighbor].owner == player_id:
                    queue.append(neighbor)
        return False

    def get_state_for_player(self, player_id: int) -> dict:
        """Return game state visible to a specific player (hides other players' cards and objectives)."""
        state = self.game.model_dump()
        for p in state["players"]:
            if p["id"] != player_id:
                p["cards"] = [{"territory": None, "symbol": "hidden"} for _ in p["cards"]]
                p["objective"] = ""
        return state
