/**
 * RISIKO — RisikoPlay-style UI
 */

// 6 fixed army colors — official Risiko
const COLORS = ['#e63946', '#2563eb', '#2a9d8f', '#f4d35e', '#222222', '#7b2d8b'];
const COLOR_NAMES = ['ROSSA', 'BLU', 'VERDE', 'GIALLA', 'NERA', 'VIOLA'];
const CONTINENT_COLORS = {
    north_america: '#5cb85c', south_america: '#d9534f', europe: '#5bc0de',
    africa: '#f0ad4e', asia: '#6b8e23', oceania: '#9b59b6',
};
const CONTINENTS_MAP = {
    north_america: ['alaska','northwest_territory','greenland','alberta','ontario','quebec','western_us','eastern_us','central_america'],
    south_america: ['venezuela','peru','brazil','argentina'],
    europe: ['iceland','scandinavia','great_britain','northern_europe','western_europe','southern_europe','ukraine'],
    africa: ['north_africa','egypt','east_africa','congo','south_africa','madagascar'],
    asia: ['ural','siberia','yakutsk','kamchatka','irkutsk','mongolia','japan','afghanistan','china','india','siam','middle_east'],
    oceania: ['indonesia','new_guinea','western_australia','eastern_australia'],
};
const TERRITORY_CONTINENT = {};
for (const [c, ts] of Object.entries(CONTINENTS_MAP)) for (const t of ts) TERRITORY_CONTINENT[t] = c;

const PHASE_TEXT = { setup: 'Posizionamento', reinforce: 'Rinforzi', attack: 'Attacco', fortify: 'Spostamento', game_over: 'Fine Partita' };
const CARD_ICON = { infantry: '🚶', cavalry: '🐴', artillery: '💣', wild: '🃏' };

let gameId = null, gameState = null, ws = null;
let selectedTerritory = null, targetTerritory = null;
let aiPlaying = false, myPlayerIndex = 0;
let labelPositions = {}; // territory -> {x, y} in SVG viewport coords
let openPanel = null;
let selectedCards = new Set();
let pendingConquest = null; // {from, to, minTroops, maxTroops} after conquering

// ===== SETUP =====
function updateSetupForm() {
    const total = parseInt(document.getElementById('total-players').value);
    const sel = document.getElementById('human-players');
    const cur = parseInt(sel.value) || 1;
    sel.innerHTML = '';
    for (let i = 1; i <= total; i++) { const o = document.createElement('option'); o.value = i; o.textContent = i; if (i === Math.min(cur, total)) o.selected = true; sel.appendChild(o); }
    const container = document.getElementById('player-names-container');
    const humans = parseInt(sel.value);
    container.innerHTML = '';

    for (let i = 0; i < humans; i++) {
        const colorOptions = COLORS.map((c, ci) =>
            `<span class="color-dot ${ci === i ? 'selected' : ''}" style="background:${c}" data-player="${i}" data-color="${c}" onclick="selectColor(${i},'${c}',this)"></span>`
        ).join('');
        container.innerHTML += `
            <div class="player-setup-row">
                <div class="color-dots" id="colors${i}">${colorOptions}</div>
                <input type="text" id="pname${i}" placeholder="${COLOR_NAMES[i]}" value="${COLOR_NAMES[i]}">
                <input type="hidden" id="color${i}" value="${COLORS[i]}">
            </div>`;
    }
}

function selectColor(playerIdx, color, el) {
    // Deselect all dots for this player
    document.querySelectorAll(`#colors${playerIdx} .color-dot`).forEach(d => d.classList.remove('selected'));
    el.classList.add('selected');
    document.getElementById(`color${playerIdx}`).value = color;
}

async function createGame() {
    const total = parseInt(document.getElementById('total-players').value);
    const humans = parseInt(document.getElementById('human-players').value);
    const difficulty = document.getElementById('ai-difficulty').value;
    const names = [], colors = [], aiFlags = [];
    for (let i = 0; i < humans; i++) { names.push(document.getElementById(`pname${i}`)?.value?.trim() || `Giocatore ${i+1}`); colors.push(document.getElementById(`color${i}`)?.value || COLORS[i]); aiFlags.push(false); }
    const used = new Set(colors); let ci = 0;
    for (let i = 0; i < total - humans; i++) { names.push(`CPU ${i+1}`); while (used.has(COLORS[ci])) ci++; colors.push(COLORS[ci]); used.add(COLORS[ci]); ci++; aiFlags.push(true); }

    const res = await fetch('api/games', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ player_names: names, player_colors: colors, ai_players: aiFlags, ai_difficulty: difficulty }) });
    const data = await res.json();
    gameId = data.game_id; gameState = data.state;
    document.getElementById('setup-screen').style.display = 'none';
    document.getElementById('game-screen').style.display = 'block';
    connectWS(); renderAll(); log('🎲 Partita iniziata!'); checkAiTurn();
}

// ===== WEBSOCKET =====
function connectWS() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const basePath = location.pathname.replace(/\/$/, '');
    ws = new WebSocket(`${proto}//${location.host}${basePath}/ws/${gameId}`);
    ws.onmessage = e => { const m = JSON.parse(e.data); if (m.type === 'state_update') { delete m.type; gameState = m; renderAll(); } };
}

// ===== RENDER =====
function renderAll() { if (!gameState) return; renderMap(); renderPlayerButtons(); renderPhaseBar(); renderActionBar(); renderCardsPanel(); renderObjectivePanel(); }

function renderMap() {
    const myId = gameState.players[myPlayerIndex].id;
    for (const [tid, st] of Object.entries(gameState.territories)) {
        const path = document.getElementById(tid);
        if (!path) continue;
        path.style.fill = CONTINENT_COLORS[TERRITORY_CONTINENT[tid]] || '#555';
        path.classList.remove('selected', 'target', 'attackable', 'reachable');
        if (tid === selectedTerritory) path.classList.add('selected');
        else if (tid === targetTerritory) path.classList.add('target');
        else if (selectedTerritory && gameState.phase === 'attack' && st.owner !== gameState.players[myPlayerIndex].id) {
            // Highlight attackable enemies adjacent to selected
            if (getNeighbors(selectedTerritory).includes(tid)) path.classList.add('attackable');
        } else if (selectedTerritory && !targetTerritory && gameState.phase === 'fortify' && st.owner === myId) {
            if (getNeighbors(selectedTerritory).includes(tid)) path.classList.add('reachable');
        }

        // Update circle + label
        const circle = document.querySelector(`circle[data-tid="${tid}"]`);
        const label = document.querySelector(`text[data-tid="${tid}"]`);
        if (circle) {
            circle.setAttribute('fill', gameState.players[st.owner].color);
            // Always white border for visibility (especially black army)
            const isDark = ['#222222', '#1d3557', '#2563eb'].includes(gameState.players[st.owner].color);
            circle.setAttribute('stroke', (st.owner === myId || isDark) ? 'white' : '#00000080');
            circle.setAttribute('stroke-width', st.owner === myId ? '2' : (isDark ? '1.5' : '0.8'));
        }
        if (label) label.textContent = st.troops;
    }
    renderAttackLines();
}

function renderAttackLines() {
    const svg = document.getElementById('attack-lines');
    svg.innerHTML = '';

    // Show incoming attack arrow when AI attacks you
    if (pendingDefense) {
        const from = labelPositions[pendingDefense.from];
        const to = labelPositions[pendingDefense.to];
        if (from && to) {
            // Arrow line
            const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
            line.setAttribute('x1', from.x); line.setAttribute('y1', from.y);
            line.setAttribute('x2', to.x); line.setAttribute('y2', to.y);
            line.setAttribute('stroke', '#ff3333');
            line.setAttribute('stroke-width', '3');
            line.setAttribute('stroke-dasharray', '8 4');
            line.setAttribute('marker-end', 'url(#arrowhead)');
            line.classList.add('attack-line');
            svg.appendChild(line);
            // Arrowhead marker
            if (!svg.querySelector('#arrowhead')) {
                const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
                defs.innerHTML = '<marker id="arrowhead" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto"><polygon points="0 0, 10 3.5, 0 7" fill="#ff3333"/></marker>';
                svg.prepend(defs);
            }
        }
        return;
    }

    // Show attackable lines when player selects a territory
    if (!selectedTerritory || gameState.phase !== 'attack') return;
    const st = gameState.territories[selectedTerritory];
    const player = gameState.players[gameState.current_player];
    if (st.owner !== player.id || st.troops < 2) return;

    const from = labelPositions[selectedTerritory];
    if (!from) return;

    const neighbors = getNeighbors(selectedTerritory);
    for (const n of neighbors) {
        if (gameState.territories[n].owner === player.id) continue;
        const to = labelPositions[n];
        if (!to) continue;
        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('x1', from.x); line.setAttribute('y1', from.y);
        line.setAttribute('x2', to.x); line.setAttribute('y2', to.y);
        line.classList.add('attack-line');
        svg.appendChild(line);
    }
}

function renderPlayerButtons() {
    const panel = document.getElementById('left-panel');
    panel.innerHTML = gameState.players.map((p, i) => {
        const isCurrent = i === gameState.current_player;
        const terrs = Object.values(gameState.territories).filter(t => t.owner === p.id).length;
        const troops = Object.entries(gameState.territories).filter(([_, t]) => t.owner === p.id).reduce((s, [_, t]) => s + t.troops, 0);
        const nextReinf = getNextReinforcements(p.id);
        const icon = p.is_ai ? '🤖' : '⚔️';
        return `<div class="player-btn ${isCurrent ? 'active' : ''} ${!p.alive ? 'dead' : ''}" style="border-color:${p.color}; color:${p.color}">
            ${icon}
            <div class="player-tooltip">
                <div class="pt-name" style="color:${p.color}">${p.name}</div>
                <div class="pt-stats">🏴 ${terrs} | 🎖️ ${troops} | +${nextReinf} prossimo turno | 🃏 ${p.cards.length}</div>
            </div>
        </div>`;
    }).join('');
}

function renderPhaseBar() {
    const p = gameState.players[gameState.current_player];
    document.getElementById('phase-player-indicator').style.background = p.color;
    document.getElementById('phase-text').textContent = `${p.name} — ${PHASE_TEXT[gameState.phase] || gameState.phase}`;
    let extra = `Turno ${gameState.turn_number}`;
    if (gameState.phase === 'reinforce') extra += ` | ${p.troops_to_place} armate`;
    if (gameState.phase === 'setup') extra += ` | ${gameState.setup_troops_remaining[p.id] || 0} rimaste`;
    if (gameState.winner !== null) extra = `🏆 ${gameState.players[gameState.winner].name} ha vinto!`;
    document.getElementById('phase-extra').textContent = extra;
}

function renderActionBar() {
    const bar = document.getElementById('action-bar');
    const phase = gameState.phase;
    const p = gameState.players[gameState.current_player];

    // Show defend button when AI attacks your territory
    if (pendingDefense) {
        bar.innerHTML = `<span class="info">⚠️ <b>${formatName(pendingDefense.to)}</b> sotto attacco da ${formatName(pendingDefense.from)}!</span><button class="btn btn-attack" onclick="defendRoll()" style="font-size:1.1rem;padding:12px 24px">🎲 DIFENDI!</button>`;
        return;
    }

    // Show troop movement slider after conquest
    if (pendingConquest) {
        const def = Math.ceil(pendingConquest.max / 2);
        bar.innerHTML = `<span class="info">🏴 Truppe extra in <b>${formatName(pendingConquest.to)}</b>?</span>
            <input type="range" id="conquest-troops" min="0" max="${pendingConquest.max}" value="${def}" oninput="document.getElementById('cval').textContent=this.value">
            <span id="cval">${def}</span>
            <button class="btn btn-attack" onclick="confirmConquestMove()">✓ OK</button>`;
        return;
    }

    if (p.is_ai) { bar.innerHTML = '<span class="info">🤖 CPU sta giocando...</span>'; return; }

    let html = '';
    if (phase === 'setup') {
        html = `<span class="info">Clicca un tuo territorio per piazzare armate (3 per turno, 1 alla volta)</span>`;
    } else if (phase === 'reinforce') {
        // Force card trade warning
        if (p.cards && p.cards.length >= 5) {
            html = `<span class="info" style="color:#f44336">⚠️ Hai ${p.cards.length} carte — devi scambiare un tris!</span>`;
            html += `<button class="btn btn-attack" onclick="togglePanel('cards')">🃏 Apri Carte</button>`;
        } else {
            html = `<span class="info">Piazza rinforzi: <b>${p.troops_to_place}</b> armate</span>`;
            html += `<button class="btn btn-secondary" onclick="undoReinforce()">↩️</button>`;
        }
    } else if (phase === 'attack') {
        if (selectedTerritory && targetTerritory) {
            const max = Math.min(3, gameState.territories[selectedTerritory].troops - 1);
            html = `<span class="info">${formatName(selectedTerritory)} → ${formatName(targetTerritory)}</span><span id="prob-display"></span>`;
            for (let d = 1; d <= max; d++) html += `<button class="btn btn-attack" onclick="doAttack(${d})">🎲×${d}</button>`;
            html += `<button class="btn btn-attack" onclick="doRapidAttack()" title="Attacco rapido">⚡</button>`;
            fetchProbability(selectedTerritory, targetTerritory);
        } else {
            html = `<span class="info">Seleziona attaccante → difensore</span>`;
        }
        html += `<button class="btn btn-secondary" onclick="endAttack()">Fine Attacco</button>`;
        html += `<button class="btn btn-end" onclick="confirmEndTurn()">Fine Turno</button>`;
    } else if (phase === 'fortify') {
        if (selectedTerritory && targetTerritory) {
            const max = gameState.territories[selectedTerritory].troops - 1;
            html = `<span class="info">${formatName(selectedTerritory)} → ${formatName(targetTerritory)}</span>`;
            html += `<input type="range" id="fort-n" min="1" max="${max}" value="1" oninput="document.getElementById('fv').textContent=this.value"><span id="fv">1</span>`;
            html += `<button class="btn btn-attack" onclick="doFortify()">Sposta</button>`;
        } else { html = `<span class="info">Seleziona sorgente → destinazione</span>`; }
        html += `<button class="btn btn-end" onclick="endTurn()">Fine Turno</button>`;
    } else if (phase === 'game_over') {
        html = `<span class="info">🏆 ${gameState.players[gameState.winner].name} ha conquistato il mondo!</span>`;
    }
    bar.innerHTML = html;
}

function renderCardsPanel() {
    const panel = document.getElementById('cards-content');
    const p = gameState.players[myPlayerIndex];
    if (!p.cards || p.cards.length === 0) { panel.innerHTML = '<p style="color:var(--text-dim);font-size:0.85rem">Nessuna carta</p>'; return; }
    let html = '<div class="card-grid">';
    p.cards.forEach((c, i) => {
        const sel = selectedCards.has(i) ? 'selected-card' : '';
        const name = c.territory ? formatName(c.territory) : 'JOLLY';
        html += `<div class="card-item ${c.symbol} ${sel}" onclick="toggleCard(${i})">${CARD_ICON[c.symbol]} ${name}</div>`;
    });
    html += '</div>';

    // Show bonus preview when 3 cards selected
    if (selectedCards.size === 3) {
        const indices = [...selectedCards];
        const selected = indices.map(i => p.cards[i]);
        const bonus = calcTradeBonus(selected);
        if (bonus > 0) {
            // Count territory bonus (+2 per card with owned territory)
            let territoryBonus = 0;
            selected.forEach(c => { if (c.territory && gameState.territories[c.territory]?.owner === p.id) territoryBonus += 2; });
            html += `<div style="margin:8px 0;padding:6px;background:rgba(255,255,255,0.05);border-radius:4px;text-align:center"><b style="color:#4caf50;font-size:1.1rem">+${bonus} armate</b>${territoryBonus ? ` <span style="color:#ff9800">+${territoryBonus} bonus territorio</span>` : ''}</div>`;
        } else {
            html += `<div style="margin:8px 0;color:#f44336;text-align:center">❌ Combinazione non valida</div>`;
        }
    }

    const canTrade = selectedCards.size === 3 && gameState.phase === 'reinforce' && gameState.players[gameState.current_player].id === p.id && calcTradeBonus([...selectedCards].map(i => p.cards[i])) > 0;
    html += `<button class="trade-btn" ${canTrade ? '' : 'disabled'} onclick="tradeSelectedCards()">Gioca Tris</button>`;
    panel.innerHTML = html;
}

function calcTradeBonus(cards) {
    // Mirror server logic: 3 cannoni=4, 3 fanti=6, 3 cavalieri=8, misto=10, jolly+2=12
    const wilds = cards.filter(c => c.symbol === 'wild').length;
    if (wilds >= 1) return 12;
    const symbols = cards.map(c => c.symbol);
    const unique = new Set(symbols);
    if (unique.size === 3) return 10; // all different
    if (unique.size === 1) {
        if (symbols[0] === 'artillery') return 4;
        if (symbols[0] === 'infantry') return 6;
        if (symbols[0] === 'cavalry') return 8;
    }
    return 0; // invalid
}

function renderObjectivePanel() {
    const p = gameState.players[myPlayerIndex];
    document.getElementById('objective-content').innerHTML = p.objective ? `<p style="color:#f9c74f;font-weight:bold">${p.objective}</p>` : '';
}

// ===== PANELS =====
function togglePanel(name) {
    const panel = document.getElementById(`panel-${name}`);
    const btn = document.getElementById(`btn-${name}`);
    if (openPanel === name) { panel.classList.add('hidden'); btn.classList.remove('open'); openPanel = null; }
    else {
        document.querySelectorAll('.slide-panel').forEach(p => p.classList.add('hidden'));
        document.querySelectorAll('.right-btn').forEach(b => b.classList.remove('open'));
        panel.classList.remove('hidden'); btn.classList.add('open'); openPanel = name;
        if (name === 'achievements') renderAchievementsPanel();
    }
}

function renderAchievementsPanel() {
    const unlocked = loadAchievements();
    const el = document.getElementById('achievements-content');
    el.innerHTML = Object.entries(ACHIEVEMENTS).map(([id, a]) => {
        const done = unlocked[id];
        return `<div class="ach-row ${done ? 'unlocked' : 'locked'}">
            <span class="ach-icon">${a.icon}</span>
            <div class="ach-info"><b>${a.name}</b><br><small>${a.desc}</small>${done ? `<br><small style="color:#2ecc71">✓ ${done.date}</small>` : ''}</div>
        </div>`;
    }).join('');
}

function toggleCard(idx) {
    if (selectedCards.has(idx)) selectedCards.delete(idx); else { if (selectedCards.size >= 3) return; selectedCards.add(idx); }
    renderCardsPanel();
}

async function tradeSelectedCards() {
    const indices = [...selectedCards].sort((a,b) => a-b);
    await apiPost(`api/games/${gameId}/trade`, { card_indices: indices });
    selectedCards.clear(); renderCardsPanel();
}

// ===== MAP INTERACTION =====
function onTerritoryClick(tid) {
    if (!gameState || aiPlaying) return;
    handleDoubleClick(tid);
    const p = gameState.players[gameState.current_player];
    if (p.is_ai) return;
    const t = gameState.territories[tid];

    if (gameState.phase === 'setup') { if (t.owner === p.id) placeSetup(tid); else showToast('Solo tuoi territori!'); }
    else if (gameState.phase === 'reinforce') { if (gameState.players[gameState.current_player].troops_to_place < 1) return; if (t.owner === p.id) placeReinforce(tid); else showToast('Solo tuoi territori!'); }
    else if (gameState.phase === 'attack') {
        if (t.owner === p.id) {
            if (t.troops < 2) { showToast('Servono almeno 2 armate!'); return; }
            selectedTerritory = tid; targetTerritory = null;
        } else if (selectedTerritory) {
            // Can always change target by clicking another enemy
            targetTerritory = tid;
        }
        renderAll();
    } else if (gameState.phase === 'fortify') {
        if (t.owner !== p.id) { showToast('Solo tuoi territori!'); return; }
        if (!selectedTerritory) {
            if (t.troops < 2) { showToast('Servono almeno 2!'); return; }
            selectedTerritory = tid;
        } else if (tid === selectedTerritory) {
            // Deselect
            selectedTerritory = null; targetTerritory = null;
        } else {
            // Check if adjacent to source → set as target, otherwise change source
            const adj = getNeighbors(selectedTerritory);
            if (adj.includes(tid)) {
                targetTerritory = tid;
            } else {
                // Change source
                if (t.troops < 2) { showToast('Servono almeno 2!'); return; }
                selectedTerritory = tid; targetTerritory = null;
            }
        }
        renderAll();
    }
}

// ===== API =====
async function placeSetup(t) { await apiPost(`api/games/${gameId}/setup`, {territory:t, troops:1}); clearSel(); checkAiTurn(); }
async function placeReinforce(t) { await apiPost(`api/games/${gameId}/reinforce`, {territory:t, troops:1}); clearSel(); checkAiTurn(); }
async function doAttack(dice) {
    if (!selectedTerritory || !targetTerritory) return;
    playDice();
    gameStats.attacks++;
    const from = selectedTerritory, target = targetTerritory;
    const res = await apiPost(`api/games/${gameId}/attack`, {from_territory: from, to_territory: target, num_dice: dice});
    if (res?.result) {
        animateDice(res.result.attacker_dice, res.result.defender_dice);
        gameStats.troopsLost += res.result.attacker_losses;
        gameStats.troopsKilled += res.result.defender_losses;
    }
    if (res?.state) {
        gameState = res.state;
        if (gameState.territories[target]?.owner === gameState.players[gameState.current_player]?.id) {
            log(`🏴 ${formatName(target)} conquistato!`);
            animateTroopMovement(from, target, dice);
            flashConquest(target);
            gameStats.conquests++;
            // Show troop movement slider
            const availableTroops = gameState.territories[from].troops - 1;
            const minTroops = 0; // Already moved dice count automatically
            if (availableTroops > 0) {
                pendingConquest = {from, to: target, min: 0, max: availableTroops};
            }
            clearSel();
        }
        renderAll();
    }
}

async function confirmConquestMove() {
    if (!pendingConquest) return;
    const troops = parseInt(document.getElementById('conquest-troops')?.value || '0');
    if (troops > 0) {
        await apiPost(`api/games/${gameId}/move`, {from_territory: pendingConquest.from, to_territory: pendingConquest.to, troops});
    }
    pendingConquest = null;
    renderAll();
}async function endAttack() { await apiPost(`api/games/${gameId}/end_attack`); clearSel(); checkAiTurn(); }
async function endTurn() { await apiPost(`api/games/${gameId}/end_turn`); clearSel(); checkAiTurn(); }
async function doFortify() { if (!selectedTerritory || !targetTerritory) return; const n = parseInt(document.getElementById('fort-n')?.value||'1'); await apiPost(`api/games/${gameId}/fortify`, {from_territory:selectedTerritory, to_territory:targetTerritory, troops:n}); clearSel(); checkAiTurn(); }

// ===== AI =====
let pendingDefense = null; // {from, to, dice} when AI attacks human

async function checkAiTurn() {
    if (!gameState || aiPlaying || gameState.phase === 'game_over') return;
    const p = gameState.players[gameState.current_player];
    if (!p.is_ai) return;

    aiPlaying = true;
    renderAll();
    await sleep(400);

    let done = false;
    while (!done && gameState.phase !== 'game_over') {
        const currentPlayer = gameState.players[gameState.current_player];
        if (!currentPlayer.is_ai) break;

        // ATTACK PHASE: check if next attack targets a human
        if (gameState.phase === 'attack') {
            const declareRes = await fetch(`api/games/${gameId}/ai_declare_attack`, {method: 'POST'});
            const declareData = await declareRes.json();

            if (!declareData.attack) {
                // No more attacks — end attack phase via ai_step
                const stepRes = await fetch(`api/games/${gameId}/ai_step`, {method: 'POST'});
                const stepData = await stepRes.json();
                if (stepData.log) logAi(stepData.log, currentPlayer.name);
                if (stepData.state) { gameState = stepData.state; renderAll(); }
                done = true;
                await sleep(300);
                break;
            }

            const atk = declareData.attack;
            const targetOwner = gameState.territories[atk.to]?.owner;
            const isMyTerritory = targetOwner === gameState.players[myPlayerIndex].id;

            if (isMyTerritory) {
                // PAUSE: show "Defend!" button and wait for human to click
                pendingDefense = atk;
                aiPlaying = false;
                renderAll();
                log(`⚠️ ${currentPlayer.name} attacca ${formatName(atk.to)}! Lancia i dadi di difesa!`);
                playClick();
                return; // Exit loop — will resume after human rolls
            } else {
                // Not my territory — resolve immediately with animation
                const res = await apiPost(`api/games/${gameId}/resolve_attack`, {from_territory: atk.from, to_territory: atk.to, num_dice: atk.dice});
                if (res?.result) {
                    animateDice(res.result.attacker_dice, res.result.defender_dice);
                    playDice();
                    log(`🤖 ${currentPlayer.name}: ${formatName(atk.from)}→${formatName(atk.to)} [${res.result.attacker_dice}] vs [${res.result.defender_dice}]`);
                }
                if (res?.state) {
                    gameState = res.state;
                    renderAll();
                    if (gameState.territories[atk.to]?.owner === currentPlayer.id) {
                        animateTroopMovement(atk.from, atk.to, atk.dice);
                        flashConquest(atk.to);
                        log(`🏴 ${currentPlayer.name} conquista ${formatName(atk.to)}!`);
                        await sleep(800);
                    }
                }
                await sleep(600);
            }
        } else {
            // Non-attack phases: use ai_step
            try {
                const res = await fetch(`api/games/${gameId}/ai_step`, {method: 'POST'});
                const d = await res.json();
                if (!d.log) { done = true; break; }
                logAi(d.log, currentPlayer.name);
                if (d.state) { gameState = d.state; renderAll(); }
                if (d.log.action === 'end_turn') { done = true; }
                // Longer delay for reinforce so user sees troop placement
                await sleep(d.log.action === 'reinforce' ? 150 : 250);
            } catch(e) { done = true; }
        }
    }

    aiPlaying = false;
    await sleep(300);
    if (gameState && gameState.phase !== 'game_over') {
        const next = gameState.players[gameState.current_player];
        if (next.is_ai) checkAiTurn();
    }
}

async function defendRoll() {
    if (!pendingDefense) return;
    const atk = pendingDefense;
    pendingDefense = null;
    aiPlaying = true;

    const res = await apiPost(`api/games/${gameId}/resolve_attack`, {from_territory: atk.from, to_territory: atk.to, num_dice: atk.dice});
    if (res?.result) {
        animateDice(res.result.attacker_dice, res.result.defender_dice);
        playDice();
        log(`🎲 Difesa: [${res.result.defender_dice}] vs attacco [${res.result.attacker_dice}] → -${res.result.attacker_losses}A -${res.result.defender_losses}D`);
    }
    if (res?.state) {
        gameState = res.state;
        const aiPlayer = gameState.players.find(p => p.is_ai && p.alive);
        if (gameState.territories[atk.to]?.owner !== gameState.players[myPlayerIndex].id) {
            flashLostTerritory(atk.to);
            log(`💀 Hai perso ${formatName(atk.to)}!`);
        }
        renderAll();
    }

    await sleep(1000);
    aiPlaying = false;
    // Continue AI turn
    checkAiTurn();
}
// logAi defined at bottom with trash talk support

// ===== HELPERS =====
async function apiPost(url, body) { try { const r = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)}); const d = await r.json(); if (!r.ok) { showToast(d.detail||'Errore'); return null; } if (d.message) log(d.message); return d; } catch(e) { showToast(e.message); return null; } }
function clearSel() { selectedTerritory = null; targetTerritory = null; }
function formatName(t) { return t.replace(/_/g,' ').replace(/\b\w/g, c=>c.toUpperCase()); }
function sleep(ms) { return new Promise(r=>setTimeout(r,ms)); }
function showToast(t, dur=3000) { const el=document.getElementById('toast'); el.textContent=t; el.classList.add('show'); setTimeout(()=>el.classList.remove('show'), dur); }
function log(t) { const el=document.getElementById('log-content'); const d=document.createElement('div'); d.className='log-entry'; d.innerHTML=t; el.prepend(d); while(el.children.length>60) el.removeChild(el.lastChild); }

function getNeighbors(tid) {
    const ADJ = {alaska:['northwest_territory','alberta','kamchatka'],northwest_territory:['alaska','alberta','ontario','greenland'],greenland:['northwest_territory','ontario','quebec','iceland'],alberta:['alaska','northwest_territory','ontario','western_us'],ontario:['northwest_territory','greenland','alberta','quebec','western_us','eastern_us'],quebec:['ontario','greenland','eastern_us'],western_us:['alberta','ontario','eastern_us','central_america'],eastern_us:['ontario','quebec','western_us','central_america'],central_america:['western_us','eastern_us','venezuela'],venezuela:['central_america','peru','brazil'],peru:['venezuela','brazil','argentina'],brazil:['venezuela','peru','argentina','north_africa'],argentina:['peru','brazil'],iceland:['greenland','scandinavia','great_britain'],scandinavia:['iceland','great_britain','northern_europe','ukraine'],great_britain:['iceland','scandinavia','northern_europe','western_europe'],northern_europe:['scandinavia','great_britain','western_europe','southern_europe','ukraine'],western_europe:['great_britain','northern_europe','southern_europe','north_africa'],southern_europe:['northern_europe','western_europe','ukraine','north_africa','egypt','middle_east'],ukraine:['scandinavia','northern_europe','southern_europe','ural','afghanistan','middle_east'],north_africa:['brazil','western_europe','southern_europe','egypt','east_africa','congo'],egypt:['southern_europe','north_africa','east_africa','middle_east'],east_africa:['north_africa','egypt','congo','south_africa','madagascar','middle_east'],congo:['north_africa','east_africa','south_africa'],south_africa:['congo','east_africa','madagascar'],madagascar:['east_africa','south_africa'],ural:['ukraine','siberia','china','afghanistan'],siberia:['ural','yakutsk','irkutsk','mongolia','china'],yakutsk:['siberia','irkutsk','kamchatka'],kamchatka:['alaska','yakutsk','irkutsk','mongolia','japan'],irkutsk:['siberia','yakutsk','kamchatka','mongolia'],mongolia:['siberia','irkutsk','kamchatka','china','japan'],japan:['kamchatka','mongolia'],afghanistan:['ukraine','ural','china','india','middle_east'],china:['ural','siberia','mongolia','afghanistan','india','siam'],india:['afghanistan','china','siam','middle_east'],siam:['china','india','indonesia'],middle_east:['southern_europe','ukraine','egypt','east_africa','afghanistan','india'],indonesia:['siam','new_guinea','western_australia'],new_guinea:['indonesia','western_australia','eastern_australia'],western_australia:['indonesia','new_guinea','eastern_australia'],eastern_australia:['new_guinea','western_australia']};
    return ADJ[tid] || [];
}


// ===== INIT MAP =====
function initMap() {
    const svgEl = document.querySelector('#map-wrapper svg');
    if (!svgEl) return;

    // Temporarily show game screen for getBBox
    const gs = document.getElementById('game-screen');
    const hidden = !gs.style.display || gs.style.display === 'none';
    if (hidden) { gs.style.display = 'block'; gs.style.visibility = 'hidden'; }

    const ns = 'http://www.w3.org/2000/svg';
    const g = document.createElementNS(ns, 'g');
    g.setAttribute('id', 'markers');
    g.setAttribute('pointer-events', 'none');

    document.querySelectorAll('.territory').forEach(path => {
        path.addEventListener('click', () => onTerritoryClick(path.id));

        try {
            const bbox = path.getBBox();
            const ctm = path.getCTM();
            const svgCtm = svgEl.getCTM();
            const pt = svgEl.createSVGPoint();
            pt.x = bbox.x + bbox.width / 2;
            pt.y = bbox.y + bbox.height / 2;
            const tp = pt.matrixTransform(ctm).matrixTransform(svgCtm.inverse());

            labelPositions[path.id] = { x: tp.x, y: tp.y };

            // Circle marker
            const c = document.createElementNS(ns, 'circle');
            c.setAttribute('cx', tp.x.toFixed(1)); c.setAttribute('cy', tp.y.toFixed(1));
            c.setAttribute('r', '7'); c.setAttribute('data-tid', path.id);
            c.setAttribute('fill', '#333'); c.setAttribute('stroke', '#000'); c.setAttribute('stroke-width', '0.8');
            g.appendChild(c);

            // Number
            const t = document.createElementNS(ns, 'text');
            t.setAttribute('x', tp.x.toFixed(1)); t.setAttribute('y', tp.y.toFixed(1));
            t.setAttribute('data-tid', path.id);
            t.setAttribute('font-family', 'Arial'); t.setAttribute('font-size', '9');
            t.setAttribute('font-weight', 'bold'); t.setAttribute('text-anchor', 'middle');
            t.setAttribute('dominant-baseline', 'central'); t.setAttribute('fill', 'white');
            t.textContent = '1';
            g.appendChild(t);
        } catch(e) {}
    });

    svgEl.appendChild(g);

    // Add territory name labels (hidden by default)
    const namesGroup = document.createElementNS(ns, 'g');
    namesGroup.setAttribute('id', 'territory-names');
    namesGroup.setAttribute('pointer-events', 'none');
    for (const [tid, pos] of Object.entries(labelPositions)) {
        const t = document.createElementNS(ns, 'text');
        t.setAttribute('x', pos.x.toFixed(1));
        t.setAttribute('y', (pos.y - 12).toFixed(1));
        t.setAttribute('class', 'territory-name');
        t.textContent = formatName(tid).replace('Northwest Territory','NW Terr.').replace('Eastern Australia','E. Australia').replace('Western Australia','W. Australia').replace('Northern Europe','N. Europe').replace('Western Europe','W. Europe').replace('Southern Europe','S. Europe').replace('Central America','C. America').replace('North Africa','N. Africa').replace('East Africa','E. Africa').replace('South Africa','S. Africa');
        namesGroup.appendChild(t);
    }
    svgEl.appendChild(namesGroup);

    // Also set attack-lines SVG viewBox to match
    const vb = svgEl.getAttribute('viewBox') || `0 0 ${svgEl.clientWidth} ${svgEl.clientHeight}`;
    document.getElementById('attack-lines').setAttribute('viewBox', vb);

    if (hidden) { gs.style.display = 'none'; gs.style.visibility = ''; }
    initZoomPan();
}

// ===== DICE =====
function animateDice(att, def) {
    const el = document.getElementById('dice-display');
    el.innerHTML = `<div class="dice-group">${att.map(() => `<span class="die att dice3d">${Math.ceil(Math.random()*6)}</span>`).join('')}</div><span class="vs">VS</span><div class="dice-group">${def.map(() => `<span class="die def dice3d">${Math.ceil(Math.random()*6)}</span>`).join('')}</div>`;

    let frame = 0;
    const interval = setInterval(() => {
        el.querySelectorAll('.die').forEach(d => { d.textContent = Math.ceil(Math.random()*6); });
        frame++;
        if (frame >= 8) {
            clearInterval(interval);
            el.innerHTML = `<div class="dice-group">${att.map(d => `<span class="die att dice3d-land">${d}</span>`).join('')}</div><span class="vs">VS</span><div class="dice-group">${def.map(d => `<span class="die def dice3d-land">${d}</span>`).join('')}</div>`;
            setTimeout(() => { el.innerHTML = ''; }, 3500);
        }
    }, 80);
}


// ===== CONQUEST ANIMATION =====
function flashConquest(tid) {
    const path = document.getElementById(tid);
    if (path) { path.classList.add('conquered'); setTimeout(() => path.classList.remove('conquered'), 1800); }
    spawnParticles(tid);
    playConquest();
}

// ===== TROOP MOVEMENT ANIMATION =====
function animateTroopMovement(fromTid, toTid, count) {
    const from = labelPositions[fromTid];
    const to = labelPositions[toTid];
    if (!from || !to) return;

    const svg = document.getElementById('attack-lines');
    const ns = 'http://www.w3.org/2000/svg';

    for (let i = 0; i < Math.min(count, 5); i++) {
        setTimeout(() => {
            const circle = document.createElementNS(ns, 'circle');
            circle.setAttribute('r', '3');
            circle.setAttribute('fill', '#ffdd44');
            circle.setAttribute('opacity', '0.9');
            const anim = document.createElementNS(ns, 'animateMotion');
            anim.setAttribute('dur', '0.6s');
            anim.setAttribute('fill', 'freeze');
            anim.setAttribute('path', `M${from.x},${from.y} L${to.x},${to.y}`);
            circle.appendChild(anim);
            svg.appendChild(circle);
            setTimeout(() => circle.remove(), 700);
        }, i * 120);
    }
}

// ===== PARTICLE EFFECTS =====
function spawnParticles(tid) {
    const pos = labelPositions[tid];
    if (!pos) return;
    const svg = document.getElementById('attack-lines');
    const ns = 'http://www.w3.org/2000/svg';
    const colors = ['#ff4444', '#ffaa00', '#ffff44', '#ff6600'];

    for (let i = 0; i < 12; i++) {
        const p = document.createElementNS(ns, 'circle');
        const angle = (Math.PI * 2 * i) / 12;
        const dist = 15 + Math.random() * 20;
        const dx = Math.cos(angle) * dist;
        const dy = Math.sin(angle) * dist;
        p.setAttribute('cx', pos.x);
        p.setAttribute('cy', pos.y);
        p.setAttribute('r', 1.5 + Math.random() * 2);
        p.setAttribute('fill', colors[i % colors.length]);
        p.setAttribute('opacity', '1');
        p.innerHTML = `
            <animate attributeName="cx" to="${pos.x + dx}" dur="0.5s" fill="freeze"/>
            <animate attributeName="cy" to="${pos.y + dy}" dur="0.5s" fill="freeze"/>
            <animate attributeName="opacity" to="0" dur="0.5s" fill="freeze"/>
            <animate attributeName="r" to="0" dur="0.5s" fill="freeze"/>
        `;
        svg.appendChild(p);
        setTimeout(() => p.remove(), 600);
    }
}

// ===== TERRITORY NAMES TOGGLE =====
let namesVisible = true;
function toggleNames() {
    namesVisible = !namesVisible;
    document.querySelectorAll('.territory-name').forEach(el => {
        el.style.display = namesVisible ? '' : 'none';
    });
    document.getElementById('btn-names').classList.toggle('open', !namesVisible);
}

// ===== ZOOM / PAN =====
let mapScale = 1, mapX = 0, mapY = 0, isPanning = false, panStart = {x:0, y:0};

function initZoomPan() {
    const wrapper = document.getElementById('map-wrapper');
    wrapper.addEventListener('wheel', e => {
        e.preventDefault();
        const delta = e.deltaY > 0 ? 0.9 : 1.1;
        mapScale = Math.max(0.5, Math.min(4, mapScale * delta));
        applyMapTransform();
    }, {passive: false});

    wrapper.addEventListener('mousedown', e => {
        if (e.button === 1 || (e.button === 0 && e.ctrlKey)) { // Middle click or ctrl+click
            isPanning = true; panStart = {x: e.clientX - mapX, y: e.clientY - mapY};
            wrapper.style.cursor = 'grabbing'; e.preventDefault();
        }
    });
    window.addEventListener('mousemove', e => {
        if (!isPanning) return;
        mapX = e.clientX - panStart.x; mapY = e.clientY - panStart.y;
        applyMapTransform();
    });
    window.addEventListener('mouseup', () => {
        if (isPanning) { isPanning = false; document.getElementById('map-wrapper').style.cursor = ''; }
    });
}

function applyMapTransform() {
    const svg = document.querySelector('#map-wrapper svg');
    if (svg) svg.style.transform = `translate(${mapX}px, ${mapY}px) scale(${mapScale})`;
}

// ===== END-GAME STATISTICS =====
let gameStats = { attacks: 0, conquests: 0, troopsLost: 0, troopsKilled: 0, turnsPlayed: 0 };

function showEndGameStats() {
    const winner = gameState.players[gameState.winner];
    const totalTerritories = Object.keys(gameState.territories).length;
    const winnerTerritories = Object.values(gameState.territories).filter(t => t.owner === winner.id).length;
    const hasConqueredAll = winnerTerritories === totalTerritories;

    const overlay = document.getElementById('stats-overlay');
    overlay.classList.remove('hidden');

    let buttons = '';
    if (hasConqueredAll) {
        buttons = `<button onclick="exitGame()">🚪 Esci</button>`;
    } else {
        buttons = `<button onclick="continueGame()">⚔️ Conquista il Mondo</button><button onclick="exitGame()" style="background:#333;margin-top:8px">🚪 Esci</button>`;
    }

    overlay.innerHTML = `<div class="stats-box">
        <h2>🏆 ${winner.name} ha vinto!</h2>
        <div style="background:#f9c74f22;border:1px solid #f9c74f;border-radius:8px;padding:12px;margin:12px 0;text-align:center"><span style="font-size:11px;color:#f9c74f;text-transform:uppercase">Obiettivo completato</span><br><span style="font-size:1.1rem;color:#f9c74f;font-weight:bold">${winner.objective || 'Conquista totale'}</span></div>
        <div class="stats-row"><span class="label">Territori</span><span class="value">${winnerTerritories}/${totalTerritories}</span></div>
        <div class="stats-row"><span class="label">Turni giocati</span><span class="value">${gameState.turn_number}</span></div>
        <div class="stats-row"><span class="label">Attacchi effettuati</span><span class="value">${gameStats.attacks}</span></div>
        <div class="stats-row"><span class="label">Territori conquistati</span><span class="value">${gameStats.conquests}</span></div>
        <div class="stats-row"><span class="label">Armate perse</span><span class="value">${gameStats.troopsLost}</span></div>
        <div class="stats-row"><span class="label">Armate eliminate</span><span class="value">${gameStats.troopsKilled}</span></div>
        ${gameState.players.map(p => `<div class="stats-row"><span class="label" style="color:${p.color}">${p.name}</span><span class="value">${p.alive ? Object.values(gameState.territories).filter(t=>t.owner===p.id).length + ' territori' : '☠️ Eliminato'}</span></div>`).join('')}
        ${buttons}
    </div>`;
    playVictory();
}

async function continueGame() {
    document.getElementById('stats-overlay').classList.add('hidden');
    const res = await apiPost(`api/games/${gameId}/continue`);
    if (res?.state) { gameState = res.state; renderAll(); }
}

function exitGame() {
    document.getElementById('stats-overlay').classList.add('hidden');
    document.getElementById('game-screen').style.display = 'none';
    document.getElementById('setup-screen').style.display = '';
    gameState = null; gameId = null;
}

function confirmExit() {
    if (!confirm('Vuoi uscire dalla partita?')) return;
    document.getElementById('stats-overlay')?.classList.add('hidden');
    document.getElementById('game-screen').style.display = 'none';
    document.getElementById('setup-screen').style.display = '';
    gameState = null; gameId = null; pendingDefense = null; pendingConquest = null;
    territoryHistory = []; gameStats = {attacks:0,conquests:0,troopsLost:0,troopsKilled:0};
}

// ===== JSON SAVE/LOAD =====
function saveGame() {
    if (!gameState) { showToast('Nessuna partita in corso'); return; }
    const data = JSON.stringify({gameState, gameStats, gameId}, null, 2);
    const blob = new Blob([data], {type: 'application/json'});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `risiko_${gameId}_turno${gameState.turn_number}.json`;
    a.click();
    showToast('💾 Partita salvata!');
}

function loadGame(event) {
    const file = event.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = async (e) => {
        try {
            const data = JSON.parse(e.target.result);
            // Send to server to restore
            const res = await fetch('api/games/load', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data.gameState),
            });
            const result = await res.json();
            gameId = result.game_id;
            gameState = result.state;
            gameStats = data.gameStats || gameStats;
            document.getElementById('setup-screen').style.display = 'none';
            document.getElementById('game-screen').style.display = 'block';
            connectWS(); renderAll();
            showToast('📂 Partita caricata!');
        } catch(err) { showToast('Errore caricamento: ' + err.message); }
    };
    reader.readAsText(file);
    event.target.value = '';
}

// ===== SOUND TOGGLE =====
function toggleSoundBtn() {
    const on = toggleSound();
    document.getElementById('btn-sound').textContent = on ? '🔊' : '🔇';
    document.getElementById('btn-sound').classList.toggle('open', !on);
}

// ===== RAPID ATTACK =====
async function doRapidAttack() {
    if (!selectedTerritory || !targetTerritory) return;
    playDice();
    const from = selectedTerritory;
    const target = targetTerritory;
    const res = await apiPost(`api/games/${gameId}/rapid_attack`, {from_territory: selectedTerritory, to_territory: targetTerritory, num_dice: 3});
    if (res) {
        log(`⚡ Attacco rapido: ${res.rounds} round`);
        if (res.results?.length) { const last = res.results[res.results.length-1]; animateDice(last.attacker_dice, last.defender_dice); }
        gameStats.attacks += res.rounds || 0;
        if (res.state) {
            gameState = res.state;
            if (gameState.territories[target]?.owner === gameState.players[gameState.current_player]?.id) {
                flashConquest(target); gameStats.conquests++; log(`🏴 ${formatName(target)} conquistato!`);
                const availableTroops = gameState.territories[from].troops - 1;
                if (availableTroops > 0) {
                    pendingConquest = {from, to: target, min: 0, max: availableTroops};
                }
            }
            clearSel(); renderAll();
        }
    }
}

// ===== UNDO REINFORCE =====
async function undoReinforce() { await apiPost(`api/games/${gameId}/undo_reinforce`); }

// ===== ATTACK PROBABILITY =====
async function fetchProbability(from, to) {
    try {
        const r = await fetch(`api/games/${gameId}/probability?from_territory=${from}&to_territory=${to}`);
        const d = await r.json();
        const el = document.getElementById('prob-display');
        if (el) { const c = d.probability > 60 ? '#4caf50' : d.probability > 35 ? '#ff9800' : '#f44336'; el.innerHTML = `<span style="color:${c};font-weight:bold;margin:0 8px">${d.probability}%</span>`; }
    } catch(e) {}
}

// ===== OBJECTIVE PROGRESS (override) =====
const _baseRenderObjective = renderObjectivePanel;
renderObjectivePanel = function() {
    const p = gameState.players[myPlayerIndex];
    const content = document.getElementById('objective-content');
    if (!p.objective) { content.innerHTML = '<p style="color:var(--text-dim)">Nessun obiettivo</p>'; return; }
    let progress = '';
    const obj = p.objective;
    const cNames = {"Europa":"europe","Oceania":"oceania","Sud America":"south_america","Nord America":"north_america","Africa":"africa","Asia":"asia"};
    for (const [name, id] of Object.entries(cNames)) {
        if (obj.includes(name)) {
            const total = CONTINENTS_MAP[id]?.length || 0;
            const owned = CONTINENTS_MAP[id]?.filter(t => gameState.territories[t]?.owner === p.id).length || 0;
            progress += `<div style="margin:3px 0;cursor:pointer" onmouseenter="highlightContinent('${id}')" onmouseleave="unhighlightContinent('${id}')"><span style="color:var(--text-dim)">${name}:</span> <b>${owned}/${total}</b> <span style="color:${owned===total?'#4caf50':'#ff9800'}">(${Math.round(owned/total*100)}%)</span></div>`;
        }
    }
    if (obj.includes('24 territori')) { const n = Object.values(gameState.territories).filter(t=>t.owner===p.id).length; progress = `<div>Territori: <b>${n}/24</b> (${Math.round(n/24*100)}%)</div>`; }
    if (obj.includes('18 territori')) { const n = Object.entries(gameState.territories).filter(([_,t])=>t.owner===p.id&&t.troops>=2).length; progress = `<div>Con 2+ armate: <b>${n}/18</b></div>`; }
    content.innerHTML = `<p style="color:#f9c74f;font-weight:bold;margin-bottom:6px">${obj}</p>${progress}`;
};

// ===== CONTINENT HIGHLIGHT =====
function highlightContinent(cid) { (CONTINENTS_MAP[cid]||[]).forEach(t => { const p = document.getElementById(t); if(p) p.style.filter='brightness(1.6)'; }); }
function unhighlightContinent(cid) { (CONTINENTS_MAP[cid]||[]).forEach(t => { const p = document.getElementById(t); if(p) p.style.filter=''; }); }

// ===== MINIMAP =====
function renderMinimap() {
    if (mapScale <= 1.2) { const m = document.getElementById('minimap'); if(m) m.style.display='none'; return; }
    let mm = document.getElementById('minimap');
    if (!mm) { mm = document.createElement('div'); mm.id = 'minimap'; mm.style.cssText = 'position:absolute;bottom:12px;right:12px;width:160px;height:110px;background:rgba(10,15,25,0.9);border-radius:8px;border:1px solid #ffffff20;z-index:10;padding:5px;'; mm.innerHTML = '<canvas width="150" height="100"></canvas>'; document.getElementById('game-screen').appendChild(mm); }
    mm.style.display = 'block';
    const canvas = mm.querySelector('canvas');
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0,0,150,100);
    for (const [tid, st] of Object.entries(gameState.territories)) { const pos = labelPositions[tid]; if(!pos) continue; ctx.fillStyle = gameState.players[st.owner].color; ctx.beginPath(); ctx.arc(pos.x/5, pos.y/5.2, 2.5, 0, Math.PI*2); ctx.fill(); }
    ctx.strokeStyle = 'white'; ctx.lineWidth = 1;
    ctx.strokeRect(-mapX/mapScale/5, -mapY/mapScale/5.2, window.innerWidth/mapScale/5, window.innerHeight/mapScale/5.2);
}

// ===== TROOP ANIMATION =====
function animateTroopPlacement(tid) {
    const label = document.querySelector(`text[data-tid="${tid}"]`);
    if (!label) return;
    const orig = label.getAttribute('font-size') || '9';
    label.setAttribute('font-size', '14');
    setTimeout(() => label.setAttribute('font-size', orig), 350);
}

// ===== THEME TOGGLE =====
let darkTheme = true;
function toggleTheme() { darkTheme = !darkTheme; document.body.style.background = darkTheme ? '#0d1117' : '#e8e8e8'; }

// ===== MATCH HISTORY =====
function saveMatchHistory() {
    if (!gameState || gameState.winner === null) return;
    const h = JSON.parse(localStorage.getItem('risiko_history') || '[]');
    h.unshift({ date: new Date().toLocaleString('it'), winner: gameState.players[gameState.winner].name, turns: gameState.turn_number, players: gameState.players.map(p=>p.name), stats: {...gameStats} });
    localStorage.setItem('risiko_history', JSON.stringify(h.slice(0, 20)));
}

// ===== HOOKS =====
const _origPlaceSetup = placeSetup;
placeSetup = async function(t) { playClick(); await _origPlaceSetup(t); animateTroopPlacement(t); };
const _origPlaceReinforce = placeReinforce;
placeReinforce = async function(t) { playClick(); await _origPlaceReinforce(t); animateTroopPlacement(t); };

const _origRenderAll = renderAll;
renderAll = function() { _origRenderAll(); if (gameState?.phase === 'game_over' && gameState.winner !== null && !document.querySelector('.stats-box')) { showEndGameStats(); saveMatchHistory(); } };

const _origApplyTransform = applyMapTransform;
applyMapTransform = function() { _origApplyTransform(); if (gameState) renderMinimap(); };

// Override logAi to show trash talk
function logAi(a, name) {
    const m = {setup:`piazza su ${formatName(a.territory||'')}`, reinforce:`+${a.troops} su ${formatName(a.territory||'')}`, attack:`${formatName(a.from||'')}→${formatName(a.to||'')}`, fortify:`sposta ${a.troops} ${formatName(a.from||'')}→${formatName(a.to||'')}`, end_attack:'fine attacchi', end_turn:'fine turno', trade_cards:'scambia carte'};
    log(`🤖 ${name}: ${m[a.action]||a.action}`);
    if (a.trash_talk) log(`💬 <i>"${a.trash_talk}"</i>`);
}



// ===== CONFIRM END TURN (if no attacks made) =====
let attacksMadeThisTurn = 0;
function confirmEndTurn() {
    if (attacksMadeThisTurn === 0 && gameState.phase === 'attack') {
        if (!confirm('Non hai ancora attaccato. Vuoi davvero finire il turno?')) return;
    }
    endTurn();
    attacksMadeThisTurn = 0;
}

// Track attacks per turn
const _origDoAttack2 = doAttack;
doAttack = async function(dice) { await _origDoAttack2(dice); attacksMadeThisTurn++; };
const _origDoRapid = doRapidAttack;
doRapidAttack = async function() { await _origDoRapid(); attacksMadeThisTurn++; };

// ===== DOUBLE-CLICK RAPID ATTACK =====
let lastClickTid = null, lastClickTime = 0;
function handleDoubleClick(tid) {
    const now = Date.now();
    if (tid === lastClickTid && now - lastClickTime < 400) {
        // Double click on enemy while attacker selected = rapid attack
        if (selectedTerritory && targetTerritory === tid && gameState.phase === 'attack') {
            doRapidAttack();
        }
    }
    lastClickTid = tid;
    lastClickTime = now;
}

// ===== KEYBOARD SHORTCUTS =====
document.addEventListener('keydown', e => {
    if (!gameState || gameState.phase === 'game_over') return;
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
    if (e.key === 'r' || e.key === 'R') { clearSel(); renderAll(); }
    if (e.key === ' ') { e.preventDefault(); if (gameState.phase === 'attack') confirmEndTurn(); else if (gameState.phase === 'fortify') endTurn(); }
    if (e.key === 'Escape') { clearSel(); pendingConquest = null; renderAll(); }
});

// ===== RED FLASH ON LOST TERRITORY =====
function flashLostTerritory(tid) {
    const path = document.getElementById(tid);
    if (path) { path.classList.add('flash-red'); setTimeout(() => path.classList.remove('flash-red'), 1500); }
}

// ===== REINFORCEMENT PREVIEW IN PLAYER PANEL =====
function getNextReinforcements(playerId) {
    const territories = Object.values(gameState.territories).filter(t => t.owner === playerId).length;
    let base = Math.max(3, Math.floor(territories / 3));
    for (const [cid, terrs] of Object.entries(CONTINENTS_MAP)) {
        if (terrs.every(t => gameState.territories[t]?.owner === playerId)) {
            const bonuses = {north_america:5, south_america:2, europe:5, africa:3, asia:7, oceania:2};
            base += bonuses[cid] || 0;
        }
    }
    return base;
}

// ===== CONTINENT OWNERSHIP GLOW =====
function renderContinentGlow() {
    if (!gameState) return;
    const myId = gameState.players[myPlayerIndex].id;
    for (const [cid, territories] of Object.entries(CONTINENTS_MAP)) {
        const allOwned = territories.every(t => gameState.territories[t]?.owner === myId);
        territories.forEach(tid => {
            const path = document.getElementById(tid);
            if (path) path.style.filter = allOwned ? 'drop-shadow(0 0 4px gold)' : '';
        });
    }
}

// ===== SKIP ANIMATIONS =====
let skipAnimations = false;
function toggleSkipAnimations() { skipAnimations = !skipAnimations; document.getElementById('btn-skip')?.classList.toggle('open', skipAnimations); showToast(skipAnimations ? '⏩ Animazioni OFF' : '▶️ Animazioni ON'); }

// ===== TERRITORY COUNT GRAPH =====
let territoryHistory = [];
function trackTerritoryCount() {
    if (!gameState) return;
    const counts = {};
    gameState.players.forEach(p => { counts[p.id] = Object.values(gameState.territories).filter(t => t.owner === p.id).length; });
    const lastTurn = territoryHistory.length > 0 ? territoryHistory[territoryHistory.length-1].turn : 0;
    if (gameState.turn_number > lastTurn) territoryHistory.push({turn: gameState.turn_number, counts});
}
function renderGraph() {
    let canvas = document.getElementById('graph-canvas');
    if (!canvas) { const d = document.createElement('div'); d.innerHTML = '<div style="margin-top:10px;font-size:0.75rem;color:var(--text-dim)">📊 Territori</div><canvas id="graph-canvas" width="250" height="80" style="width:100%;background:rgba(0,0,0,0.2);border-radius:4px;margin-top:4px"></canvas>'; document.getElementById('objective-content')?.appendChild(d); canvas = document.getElementById('graph-canvas'); }
    if (!canvas || territoryHistory.length < 2) return;
    const ctx = canvas.getContext('2d'); ctx.clearRect(0,0,250,80);
    const max = territoryHistory.length;
    gameState.players.forEach(p => { ctx.strokeStyle = p.color; ctx.lineWidth = 1.5; ctx.beginPath(); territoryHistory.forEach((h,i) => { const x = i/(max-1)*245+2; const y = 78-(h.counts[p.id]||0)/42*75; i===0?ctx.moveTo(x,y):ctx.lineTo(x,y); }); ctx.stroke(); });
}

// ===== TUTORIAL =====
const TUTORIAL_STEPS = [
    "🎲 Benvenuto! Piazza le armate sui tuoi territori (3 per turno, 1 alla volta)",
    "🛡️ Fase Rinforzi: ricevi armate (territori÷3 + bonus continenti). Piazzale dove vuoi!",
    "⚔️ Fase Attacco: clicca tuo territorio → nemico adiacente → scegli dadi. ⚡ = attacco rapido!",
    "🚚 Spostamento: muovi armate tra territori collegati (tuoi). Un solo spostamento per turno.",
    "🎯 Apri il pannello obiettivo per vedere la tua missione segreta. Buona fortuna!",
];
let tutorialStep = 0;
function showTutorial() {
    if (localStorage.getItem('risiko_tutorial_done')) return;
    showTutorialStep();
}
function showTutorialStep() {
    if (tutorialStep >= TUTORIAL_STEPS.length) { localStorage.setItem('risiko_tutorial_done','1'); document.getElementById('tutorial-overlay')?.remove(); return; }
    let ov = document.getElementById('tutorial-overlay');
    if (!ov) { ov = document.createElement('div'); ov.id = 'tutorial-overlay'; ov.style.cssText = 'position:absolute;top:55px;left:50%;transform:translateX(-50%);background:rgba(10,15,25,0.95);padding:14px 22px;border-radius:10px;border:2px solid #f9c74f;z-index:100;max-width:420px;text-align:center;backdrop-filter:blur(8px)'; document.getElementById('game-screen').appendChild(ov); }
    ov.innerHTML = `<p style="margin-bottom:10px;color:#f9c74f;font-size:0.9rem">${TUTORIAL_STEPS[tutorialStep]}</p><button onclick="nextTutorialStep()" style="padding:6px 16px;border:none;border-radius:4px;background:#2563eb;color:white;cursor:pointer;font-weight:bold">${tutorialStep<TUTORIAL_STEPS.length-1?'Avanti →':'Ho capito! ✓'}</button><button onclick="skipTutorial()" style="padding:6px 12px;border:none;border-radius:4px;background:#333;color:#aaa;cursor:pointer;margin-left:8px">Salta</button>`;
}
function nextTutorialStep() { tutorialStep++; showTutorialStep(); }
function skipTutorial() { localStorage.setItem('risiko_tutorial_done','1'); document.getElementById('tutorial-overlay')?.remove(); }

// ===== ENHANCED HOOKS =====
const _finalRenderAll = renderAll;
renderAll = function() { _finalRenderAll(); renderContinentGlow(); trackTerritoryCount(); if (openPanel === 'objective') renderGraph(); };
const _finalSleep = sleep;
sleep = function(ms) { return skipAnimations ? _finalSleep(30) : _finalSleep(ms); };

// Show tutorial on first game start
const _finalCreateGame = createGame;
createGame = async function() { await _finalCreateGame(); showTutorial(); };

document.addEventListener('DOMContentLoaded', updateSetupForm);

// ===== SPEED MODE =====
let speedMode = false, speedTimer = null, speedSeconds = 0;
const SPEED_LIMIT = 10;

function startSpeedTimer() {
    if (!speedMode || !gameState || gameState.phase === 'game_over' || gameState.phase === 'setup') return;
    const p = gameState.players[gameState.current_player];
    if (p.is_ai) return;
    stopSpeedTimer();
    speedSeconds = SPEED_LIMIT;
    updateTimerDisplay();
    document.getElementById('speed-timer').classList.remove('hidden');
    speedTimer = setInterval(() => {
        speedSeconds--;
        updateTimerDisplay();
        if (speedSeconds <= 0) { stopSpeedTimer(); autoSkipTurn(); }
    }, 1000);
}

function stopSpeedTimer() {
    if (speedTimer) { clearInterval(speedTimer); speedTimer = null; }
    document.getElementById('speed-timer').classList.add('hidden');
}

function updateTimerDisplay() {
    const el = document.getElementById('speed-timer');
    el.textContent = `⏱️ ${speedSeconds}s`;
    el.className = speedSeconds <= 3 ? 'speed-critical' : '';
}

async function autoSkipTurn() {
    if (!gameState || gameState.phase === 'game_over') return;
    showToast('⏱️ Tempo scaduto!');
    if (gameState.phase === 'reinforce') {
        // Auto-place remaining troops randomly
        const p = gameState.players[gameState.current_player];
        while (p.troops_to_place > 0 && gameState.phase === 'reinforce') {
            const owned = Object.entries(gameState.territories).filter(([_, t]) => t.owner === p.id);
            if (!owned.length) break;
            const [tid] = owned[Math.floor(Math.random() * owned.length)];
            await apiPost(`api/games/${gameId}/reinforce`, {territory: tid, troops: 1});
        }
    } else if (gameState.phase === 'attack') {
        await apiPost(`api/games/${gameId}/end_turn`);
    } else if (gameState.phase === 'fortify') {
        await apiPost(`api/games/${gameId}/end_turn`);
    }
    clearSel(); checkAiTurn();
}

// Hook into renderAll to restart timer on phase/player change
let _lastTimerKey = '';
const _speedRenderAll = renderAll;
renderAll = function() {
    _speedRenderAll();
    if (!speedMode || !gameState) return;
    const key = `${gameState.current_player}-${gameState.phase}`;
    if (key !== _lastTimerKey) { _lastTimerKey = key; startSpeedTimer(); }
};

// Hook createGame to read speed mode checkbox
const _origCreateGame2 = createGame;
createGame = async function() {
    speedMode = document.getElementById('speed-mode').checked;
    await _origCreateGame2();
    if (speedMode) log('⚡ SPEED MODE attivo — 10 secondi per turno!');
};

// ===== TOURNAMENT MODE =====
let tournamentId = null, tournamentState = null;

async function createTournament() {
    const total = parseInt(document.getElementById('total-players').value);
    const humans = parseInt(document.getElementById('human-players').value);
    const difficulty = document.getElementById('ai-difficulty').value;
    const names = [], colors = [], aiFlags = [];
    for (let i = 0; i < humans; i++) { names.push(document.getElementById(`pname${i}`)?.value?.trim() || `Giocatore ${i+1}`); colors.push(document.getElementById(`color${i}`)?.value || COLORS[i]); aiFlags.push(false); }
    const used = new Set(colors); let ci = 0;
    for (let i = 0; i < total - humans; i++) { names.push(`CPU ${i+1}`); while (used.has(COLORS[ci])) ci++; colors.push(COLORS[ci]); used.add(COLORS[ci]); ci++; aiFlags.push(true); }

    const res = await fetch('api/tournaments?best_of=3', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ player_names: names, player_colors: colors, ai_players: aiFlags, ai_difficulty: difficulty }) });
    const data = await res.json();
    tournamentId = data.tournament_id;
    tournamentState = data.tournament;
    showToast('🏆 Torneo iniziato! Best of 3');
    startNextTournamentMatch();
}

async function startNextTournamentMatch() {
    const res = await fetch(`api/tournaments/${tournamentId}/next_match`, { method: 'POST' });
    const data = await res.json();
    gameId = data.game_id; gameState = data.state;
    document.getElementById('setup-screen').style.display = 'none';
    document.getElementById('game-screen').style.display = 'block';
    connectWS(); renderAll();
    log(`🏆 Torneo — Partita ${data.match_number} di ${tournamentState.best_of}`);
    showTournamentProgress();
    checkAiTurn();
}

function showTournamentProgress() {
    if (!tournamentState) return;
    const ov = document.getElementById('tournament-overlay');
    ov.classList.remove('hidden');
    const scores = tournamentState.players.map(p =>
        `<span style="color:${p.color};font-weight:bold">${p.name}: ${p.wins}</span>`
    ).join(' — ');
    ov.innerHTML = `<div class="tournament-bar">🏆 Partita ${tournamentState.current_match + 1}/${tournamentState.best_of} | ${scores}</div>`;
    setTimeout(() => ov.classList.add('hidden'), 4000);
}

async function handleTournamentGameOver() {
    if (!tournamentId || !tournamentState || gameState.winner === null) return false;
    const winner = gameState.players[gameState.winner];

    const res = await fetch(`api/tournaments/${tournamentId}/record_result?winner_name=${encodeURIComponent(winner.name)}&turns=${gameState.turn_number}`, { method: 'POST' });
    tournamentState = await res.json();

    // Update local wins
    for (const p of tournamentState.players) {
        if (p.name === winner.name) { p.wins = p.wins; break; }
    }

    if (tournamentState.winner) {
        // Tournament over!
        showTournamentWinner();
        return true;
    }

    // Show match result and start next
    showTournamentMatchResult(winner.name);
    return true;
}

function showTournamentMatchResult(winnerName) {
    const overlay = document.getElementById('stats-overlay');
    overlay.classList.remove('hidden');
    const scores = tournamentState.players.map(p =>
        `<div class="stats-row"><span class="label" style="color:${p.color}">${p.name}</span><span class="value">${p.wins} vittorie</span></div>`
    ).join('');
    overlay.innerHTML = `<div class="stats-box">
        <h2>🏆 Partita ${tournamentState.current_match}/${tournamentState.best_of}</h2>
        <p style="color:#f9c74f;font-size:1.1rem">${winnerName} vince questa partita!</p>
        ${scores}
        <button onclick="nextTournamentMatch()">⚔️ Prossima Partita</button>
    </div>`;
}

function showTournamentWinner() {
    const overlay = document.getElementById('stats-overlay');
    overlay.classList.remove('hidden');
    const scores = tournamentState.players.map(p =>
        `<div class="stats-row"><span class="label" style="color:${p.color}">${p.name}</span><span class="value">${p.wins} vittorie</span></div>`
    ).join('');
    overlay.innerHTML = `<div class="stats-box">
        <h2>🏆🏆🏆 TORNEO FINITO!</h2>
        <p style="color:#f9c74f;font-size:1.3rem;font-weight:bold">${tournamentState.winner} è il campione!</p>
        ${scores}
        <p style="color:#aaa;font-size:0.8rem;margin-top:12px">Classifica ELO aggiornata</p>
        <button onclick="endTournament()">🚪 Torna al Menu</button>
    </div>`;
    playVictory();
}

async function nextTournamentMatch() {
    document.getElementById('stats-overlay').classList.add('hidden');
    gameStats = {attacks:0,conquests:0,troopsLost:0,troopsKilled:0};
    territoryHistory = [];
    await startNextTournamentMatch();
}

function endTournament() {
    document.getElementById('stats-overlay').classList.add('hidden');
    document.getElementById('game-screen').style.display = 'none';
    document.getElementById('setup-screen').style.display = '';
    tournamentId = null; tournamentState = null;
    gameState = null; gameId = null;
    loadEloRankings();
}

async function loadEloRankings() {
    try {
        const res = await fetch('api/elo');
        const data = await res.json();
        const section = document.getElementById('elo-section');
        if (!data.rankings || data.rankings.length === 0) { section.innerHTML = ''; return; }
        section.innerHTML = `<h3>🏅 Classifica ELO</h3><div class="elo-list">${
            data.rankings.slice(0, 10).map((r, i) =>
                `<div class="elo-row"><span class="elo-rank">#${i+1}</span><span class="elo-name">${r.name}</span><span class="elo-score">${r.elo}</span></div>`
            ).join('')
        }</div>`;
    } catch(e) { /* ignore */ }
}

// Override game over to handle tournament
const _origShowEndGameStats = showEndGameStats;
showEndGameStats = function() {
    if (tournamentId) { handleTournamentGameOver(); return; }
    _origShowEndGameStats();
};

// Load ELO on page load
document.addEventListener('DOMContentLoaded', loadEloRankings);

// Achievement tracking hooks
const _achFlashConquest = flashConquest;
flashConquest = function(tid) { _achFlashConquest(tid); achievementTracking.conquestsThisTurn++; };
const _achFlashLost = flashLostTerritory;
flashLostTerritory = function(tid) { _achFlashLost(tid); achievementTracking.lostTerritory = true; };

// Reset tracking on new game
const _achCreateGame = createGame;
createGame = async function() {
    achievementTracking = { conquestsThisTurn: 0, defensesSuccessful: 0, tradesThisGame: 0, lostTerritory: false };
    await _achCreateGame();
};

// ===== ACHIEVEMENTS =====
const ACHIEVEMENTS = {
    first_blood: { icon: '🗡️', name: 'Prima Conquista', desc: 'Conquista il tuo primo territorio' },
    continent_master: { icon: '🌍', name: 'Padrone del Continente', desc: 'Completa un continente intero' },
    unstoppable: { icon: '🔥', name: 'Inarrestabile', desc: 'Conquista 5 territori in un turno' },
    fortress: { icon: '🏰', name: 'Fortezza', desc: 'Difendi con successo 10 attacchi in una partita' },
    blitz: { icon: '⚡', name: 'Blitz', desc: 'Vinci una partita in meno di 15 turni' },
    survivor: { icon: '🛡️', name: 'Sopravvissuto', desc: 'Vinci senza mai perdere un territorio' },
    card_master: { icon: '🃏', name: 'Maestro di Carte', desc: 'Scambia 5 tris in una partita' },
    world_domination: { icon: '👑', name: 'Dominazione Totale', desc: 'Conquista tutti i 42 territori' },
    speed_demon: { icon: '⏱️', name: 'Speed Demon', desc: 'Vinci in Speed Mode' },
    tournament_champ: { icon: '🏆', name: 'Campione del Torneo', desc: 'Vinci un torneo' },
};

let achievementTracking = { conquestsThisTurn: 0, defensesSuccessful: 0, tradesThisGame: 0, lostTerritory: false };

function loadAchievements() { return JSON.parse(localStorage.getItem('risiko_achievements') || '{}'); }
function saveAchievement(id) {
    const achs = loadAchievements();
    if (achs[id]) return; // Already unlocked
    achs[id] = { date: new Date().toLocaleString('it') };
    localStorage.setItem('risiko_achievements', JSON.stringify(achs));
    showAchievementNotification(id);
}

function showAchievementNotification(id) {
    const a = ACHIEVEMENTS[id];
    if (!a) return;
    const el = document.createElement('div');
    el.className = 'achievement-popup';
    el.innerHTML = `<span class="ach-icon">${a.icon}</span><div><b>Achievement Sbloccato!</b><br>${a.name}</div>`;
    document.body.appendChild(el);
    setTimeout(() => el.classList.add('show'), 50);
    setTimeout(() => { el.classList.remove('show'); setTimeout(() => el.remove(), 300); }, 3500);
}

function checkAchievements() {
    if (!gameState) return;
    const myId = gameState.players[myPlayerIndex].id;
    const myTerritories = Object.entries(gameState.territories).filter(([_, t]) => t.owner === myId);

    // First conquest
    if (myTerritories.length > (gameState.players.length > 0 ? Math.floor(Object.keys(gameState.territories).length / gameState.players.length) : 0)) {
        saveAchievement('first_blood');
    }

    // Continent master
    const cmap = CONTINENTS_MAP;
    for (const [_, terrs] of Object.entries(cmap)) {
        if (terrs.every(t => gameState.territories[t]?.owner === myId)) {
            saveAchievement('continent_master');
            break;
        }
    }

    // Unstoppable (5 conquests in one turn)
    if (achievementTracking.conquestsThisTurn >= 5) saveAchievement('unstoppable');

    // World domination
    if (myTerritories.length === Object.keys(gameState.territories).length) saveAchievement('world_domination');

    // Card master
    if (achievementTracking.tradesThisGame >= 5) saveAchievement('card_master');
}

function checkWinAchievements() {
    if (!gameState || gameState.winner !== myPlayerIndex) return;
    if (gameState.turn_number < 15) saveAchievement('blitz');
    if (!achievementTracking.lostTerritory) saveAchievement('survivor');
    if (speedMode) saveAchievement('speed_demon');
    if (tournamentState?.winner === gameState.players[myPlayerIndex].name) saveAchievement('tournament_champ');
    if (achievementTracking.defensesSuccessful >= 10) saveAchievement('fortress');
}

// Hook into game events
const _achRenderAll = renderAll;
renderAll = function() {
    _achRenderAll();
    if (gameState) checkAchievements();
    if (gameState?.phase === 'game_over' && gameState.winner !== null) checkWinAchievements();
};

// Track conquests per turn
let _lastTurnForAch = 0;
const _achOrigRenderAll2 = renderAll;
renderAll = function() {
    _achOrigRenderAll2();
    if (gameState && gameState.turn_number !== _lastTurnForAch) {
        _lastTurnForAch = gameState.turn_number;
        achievementTracking.conquestsThisTurn = 0;
    }
};
