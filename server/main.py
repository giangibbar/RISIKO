"""Risiko FastAPI server — REST + WebSocket API."""

import json
import asyncio
from typing import Dict, List
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.gzip import GZipMiddleware

from .models import (
    CreateGameRequest, PlaceTroopsRequest, AttackRequest,
    FortifyRequest, TradeCardsRequest, GamePhase,
)
from .game_engine import GameEngine
from .ai_player import ai_play_turn, reset_card_memory
from .tournament import (
    create_tournament, record_match_result, get_tournament,
    get_elo_rankings, TournamentState,
)

app = FastAPI(title="Risiko", version="1.0.0")
app.add_middleware(GZipMiddleware, minimum_size=500)


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


# Game storage (in-memory for now)
games: Dict[str, GameEngine] = {}

# WebSocket connections per game
connections: Dict[str, List[WebSocket]] = {}


# --- Broadcast helper ---

async def broadcast(game_id: str, message: dict):
    """Send message to all connected clients for a game."""
    for ws in connections.get(game_id, []):
        try:
            await ws.send_json(message)
        except Exception:
            pass


async def broadcast_state(game_id: str):
    """Broadcast full game state to all players."""
    engine = games[game_id]
    state = engine.game.model_dump()
    state["type"] = "state_update"
    await broadcast(game_id, state)


# --- REST Endpoints ---

@app.post("/api/games")
async def create_game(req: CreateGameRequest):
    """Create a new game."""
    if not 2 <= len(req.player_names) <= 6:
        raise HTTPException(400, "Need 2-6 players")
    engine = GameEngine.create_game(req.player_names, req.player_colors, req.ai_players or None, req.ai_difficulty)
    games[engine.game.id] = engine
    connections[engine.game.id] = []
    return {"game_id": engine.game.id, "state": engine.game.model_dump()}


@app.get("/api/games/{game_id}")
async def get_game(game_id: str):
    """Get current game state."""
    engine = _get_engine(game_id)
    return engine.game.model_dump()


@app.post("/api/games/{game_id}/setup")
async def setup_place(game_id: str, req: PlaceTroopsRequest):
    """Place troops during setup phase."""
    engine = _get_engine(game_id)
    player_id = engine.game.current_player
    msg = engine.place_setup_troops(player_id, req.territory, req.troops)
    await broadcast_state(game_id)
    return {"message": msg}


@app.post("/api/games/{game_id}/reinforce")
async def reinforce(game_id: str, req: PlaceTroopsRequest):
    """Place reinforcement troops."""
    engine = _get_engine(game_id)
    player_id = engine.game.players[engine.game.current_player].id
    msg = engine.place_troops(player_id, req.territory, req.troops)
    await broadcast_state(game_id)
    return {"message": msg}


@app.post("/api/games/{game_id}/trade")
async def trade_cards(game_id: str, req: TradeCardsRequest):
    """Trade cards for bonus troops."""
    engine = _get_engine(game_id)
    player_id = engine.game.players[engine.game.current_player].id
    msg = engine.trade_cards(player_id, req.card_indices)
    await broadcast_state(game_id)
    return {"message": msg}


@app.post("/api/games/{game_id}/attack")
async def attack(game_id: str, req: AttackRequest):
    """Execute an attack."""
    engine = _get_engine(game_id)
    player_id = engine.game.players[engine.game.current_player].id
    result = engine.attack(player_id, req.from_territory, req.to_territory, req.num_dice)
    await broadcast(game_id, {
        "type": "combat_result",
        "from": req.from_territory,
        "to": req.to_territory,
        "result": result.model_dump(),
    })
    await broadcast_state(game_id)
    return {"result": result.model_dump(), "state": engine.game.model_dump(), "last_dice": getattr(engine, '_last_attack_dice', 1)}


@app.post("/api/games/{game_id}/end_attack")
async def end_attack(game_id: str):
    """End attack phase, move to fortify."""
    engine = _get_engine(game_id)
    player_id = engine.game.players[engine.game.current_player].id
    msg = engine.end_attack_phase(player_id)
    await broadcast_state(game_id)
    return {"message": msg}


@app.get("/api/games/{game_id}/probability")
async def get_probability(game_id: str, from_territory: str, to_territory: str):
    """Get attack win probability."""
    from .combat import attack_probability
    engine = _get_engine(game_id)
    att = engine.game.territories[from_territory].troops
    defe = engine.game.territories[to_territory].troops
    prob = attack_probability(att, defe)
    return {"probability": prob, "attacker": att, "defender": defe}


@app.post("/api/games/{game_id}/rapid_attack")
async def rapid_attack(game_id: str, req: AttackRequest):
    """Attack repeatedly until conquest or failure."""
    engine = _get_engine(game_id)
    player_id = engine.game.players[engine.game.current_player].id
    results = engine.rapid_attack(player_id, req.from_territory, req.to_territory)
    await broadcast_state(game_id)
    return {"results": [r.model_dump() for r in results], "rounds": len(results), "state": engine.game.model_dump()}


@app.post("/api/games/{game_id}/undo_reinforce")
async def undo_reinforce(game_id: str):
    """Undo last reinforcement."""
    engine = _get_engine(game_id)
    player_id = engine.game.players[engine.game.current_player].id
    msg = engine.undo_reinforce(player_id)
    await broadcast_state(game_id)
    return {"message": msg}


@app.post("/api/games/{game_id}/fortify")
async def fortify(game_id: str, req: FortifyRequest):
    """Fortify — move troops between territories."""
    engine = _get_engine(game_id)
    player_id = engine.game.players[engine.game.current_player].id
    msg = engine.fortify(player_id, req.from_territory, req.to_territory, req.troops)
    await broadcast_state(game_id)
    return {"message": msg}


@app.post("/api/games/{game_id}/end_turn")
async def end_turn(game_id: str):
    """End current turn (skip fortify)."""
    engine = _get_engine(game_id)
    player_id = engine.game.players[engine.game.current_player].id
    msg = engine.end_turn(player_id)
    await broadcast_state(game_id)
    return {"message": msg}


@app.post("/api/games/{game_id}/continue")
async def continue_game(game_id: str):
    """Continue playing after objective victory (to conquer the world)."""
    engine = _get_engine(game_id)
    if engine.game.phase != GamePhase.GAME_OVER:
        raise HTTPException(400, "Game is not over")
    # Remove objective-based win, continue current player's turn
    engine.game.phase = GamePhase.ATTACK
    engine.game.winner = None
    # Clear all objectives so they don't trigger again
    for p in engine.game.players:
        p.objective = ""
    await broadcast_state(game_id)
    return {"state": engine.game.model_dump()}


@app.post("/api/games/{game_id}/move")
async def move_troops(game_id: str, req: FortifyRequest):
    """Move troops after conquest."""
    engine = _get_engine(game_id)
    player_id = engine.game.players[engine.game.current_player].id
    msg = engine.move_after_conquest(player_id, req.from_territory, req.to_territory, req.troops)
    await broadcast_state(game_id)
    return {"message": msg}


@app.post("/api/games/{game_id}/ai_turn")
async def ai_turn(game_id: str):
    """Execute AI turn for current player (must be AI)."""
    engine = _get_engine(game_id)
    player = engine.game.players[engine.game.current_player]
    if not player.is_ai:
        raise HTTPException(400, "Current player is not AI")

    logs = await asyncio.to_thread(ai_play_turn, engine.game, engine, difficulty=player.ai_difficulty)
    await broadcast_state(game_id)
    return {"logs": logs, "state": engine.game.model_dump()}


@app.post("/api/games/{game_id}/ai_step")
async def ai_step(game_id: str):
    """Execute ONE AI action (for step-by-step animation)."""
    from .ai_player import ai_play_step
    engine = _get_engine(game_id)
    player = engine.game.players[engine.game.current_player]
    if not player.is_ai:
        raise HTTPException(400, "Current player is not AI")

    log_entry = await asyncio.to_thread(ai_play_step, engine.game, engine, difficulty=player.ai_difficulty)
    await broadcast_state(game_id)
    return {"log": log_entry, "state": engine.game.model_dump(), "done": log_entry is None or log_entry.get("action") in ("end_turn", "end_attack")}


@app.post("/api/games/{game_id}/ai_declare_attack")
async def ai_declare_attack(game_id: str):
    """AI picks an attack target but doesn't resolve yet. Returns from/to for defender to roll."""
    from .ai_player import ai_pick_next_attack
    engine = _get_engine(game_id)
    player = engine.game.players[engine.game.current_player]
    if not player.is_ai:
        raise HTTPException(400, "Current player is not AI")
    if engine.game.phase != GamePhase.ATTACK:
        return {"attack": None}

    attack = ai_pick_next_attack(engine.game, engine, player.ai_difficulty)
    if not attack:
        return {"attack": None}
    return {"attack": {"from": attack[0], "to": attack[1], "dice": attack[2]}}


@app.post("/api/games/{game_id}/resolve_attack")
async def resolve_attack(game_id: str, req: AttackRequest):
    """Resolve a declared attack (defender confirmed roll)."""
    engine = _get_engine(game_id)
    player_id = engine.game.players[engine.game.current_player].id
    result = engine.attack(player_id, req.from_territory, req.to_territory, req.num_dice)
    await broadcast_state(game_id)
    return {"result": result.model_dump(), "state": engine.game.model_dump()}


@app.post("/api/games/load")
async def load_game(state: dict):
    """Load a saved game state from JSON."""
    from .models import GameState
    game = GameState(**state)
    engine = GameEngine(game)
    games[game.id] = engine
    connections[game.id] = []
    return {"game_id": game.id, "state": engine.game.model_dump()}


# --- Tournament Endpoints ---

@app.post("/api/tournaments")
async def create_tournament_endpoint(req: CreateGameRequest, best_of: int = 3):
    """Create a new tournament (best of N)."""
    if not 2 <= len(req.player_names) <= 6:
        raise HTTPException(400, "Need 2-6 players")
    ai_players = req.ai_players or [False] * len(req.player_names)
    tournament = create_tournament(
        req.player_names, req.player_colors, ai_players,
        req.ai_difficulty, best_of
    )
    return {"tournament_id": tournament.id, "tournament": tournament.model_dump()}


@app.get("/api/tournaments/{tournament_id}")
async def get_tournament_endpoint(tournament_id: str):
    """Get tournament state."""
    t = get_tournament(tournament_id)
    if not t:
        raise HTTPException(404, "Tournament not found")
    return t.model_dump()


@app.post("/api/tournaments/{tournament_id}/next_match")
async def start_next_match(tournament_id: str):
    """Start the next match in the tournament."""
    t = get_tournament(tournament_id)
    if not t:
        raise HTTPException(404, "Tournament not found")
    if t.winner:
        raise HTTPException(400, "Tournament already finished")

    # Create a new game with the same players
    names = [p.name for p in t.players]
    colors = [p.color for p in t.players]
    ai_flags = [p.is_ai for p in t.players]
    difficulty = t.players[0].ai_difficulty

    engine = GameEngine.create_game(names, colors, ai_flags, difficulty)
    games[engine.game.id] = engine
    connections[engine.game.id] = []
    t.current_game_id = engine.game.id

    return {"game_id": engine.game.id, "state": engine.game.model_dump(), "match_number": t.current_match + 1}


@app.post("/api/tournaments/{tournament_id}/record_result")
async def record_result(tournament_id: str, winner_name: str, turns: int):
    """Record match result and advance tournament."""
    t = get_tournament(tournament_id)
    if not t:
        raise HTTPException(404, "Tournament not found")
    if t.winner:
        raise HTTPException(400, "Tournament already finished")

    # Clean up old game card memory
    if t.current_game_id:
        reset_card_memory(t.current_game_id)

    t = record_match_result(tournament_id, winner_name, turns)
    return t.model_dump()


@app.get("/api/elo")
async def get_elo():
    """Get ELO rankings."""
    return {"rankings": get_elo_rankings()}


# --- WebSocket ---

@app.websocket("/ws/{game_id}")
async def websocket_endpoint(websocket: WebSocket, game_id: str):
    """WebSocket for real-time game updates."""
    if game_id not in games:
        await websocket.close(code=4004)
        return

    await websocket.accept()
    connections[game_id].append(websocket)

    try:
        # Send current state on connect
        engine = games[game_id]
        await websocket.send_json({
            "type": "state_update",
            **engine.game.model_dump(),
        })

        # Keep alive and handle client messages
        while True:
            data = await websocket.receive_text()
            # Client can send actions via WS too (future)
    except WebSocketDisconnect:
        connections[game_id].remove(websocket)


# --- Static files (client) ---

@app.middleware("http")
async def static_cache_headers(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "public, max-age=86400"
    return response

app.mount("/static", StaticFiles(directory="client"), name="static")


@app.get("/")
async def index():
    return FileResponse("client/index.html", headers={"Cache-Control": "public, max-age=3600"})


# --- Helpers ---

def _get_engine(game_id: str) -> GameEngine:
    if game_id not in games:
        raise HTTPException(404, f"Game {game_id} not found")
    return games[game_id]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
