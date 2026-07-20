# ⚔️ RISIKO — Web Game

Un clone completo del gioco da tavolo **RisiKo!** giocabile nel browser, con AI avversaria e regole ufficiali italiane.

![Python](https://img.shields.io/badge/Python-3.12-blue) ![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green) ![License](https://img.shields.io/badge/License-MIT-yellow)

## 🎮 Features

- **Mappa mondo interattiva** — SVG da Wikipedia con 42 territori cliccabili, zoom/pan, nomi sempre visibili
- **Regole ufficiali italiane** — difensore 3 dadi, tris carte (4/6/8/10/12), obiettivi segreti, spostamento tra territori connessi
- **AI intelligente** — 3 livelli × 3 personalità + memoria carte, valutazione rischio, difesa continenti, trash talk
- **3-6 giocatori** — umani e/o CPU, hot-seat locale
- **🌐 Multiplayer online** — lobby con codice condivisibile: ogni giocatore entra da un browser diverso, sceglie nickname e si mette "pronto"; l'host configura CPU/difficoltà e avvia. Turni validati lato server (token per posto)
- **Lancia i dadi di difesa** — quando l'AI ti attacca, sei TU a premere il pulsante
- **Indicatori di movimento** — linee tratteggiate rosse per gli attacchi possibili, blu per gli spostamenti
- **Modalità Torneo** — best of 3, classifica ELO locale persistente
- **Speed Mode** — turni da 10 secondi, chi non agisce perde il turno
- **Achievements** — 10 obiettivi sbloccabili con notifiche popup
- **Animazioni** — dadi 3D con CSS transforms, truppe che volano tra territori, particelle su conquista
- **Interfaccia stile RisikoPlay** — mappa fullscreen, pannelli overlay, frecce attacco animate, colori continente vivaci
- **Suoni** — effetti audio generati con Web Audio API
- **Salva/Carica** — esporta partita come JSON, riprendi quando vuoi
- **Tutorial** — guida interattiva alla prima partita
- **Statistiche** — grafico territori nel tempo, stats fine partita, storico in localStorage

## 🚀 Quick Start

```bash
cd RISIKO
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
./run.sh
```

Apri `http://localhost:8080` nel browser.

## 🌐 Multiplayer Online

Gioca da browser/dispositivi diversi tramite una **lobby**:

1. Un giocatore preme **🌐 Crea Partita Online** → entra nella lobby, sceglie il nickname, imposta numero di CPU e difficoltà, e ottiene un **codice** (+ link condivisibile).
2. Gli altri incollano il codice in **🔗 Unisciti con Codice** (o aprono il link) → entrano nella lobby e scelgono il nickname.
3. Ogni giocatore preme **Sono Pronto**; quando tutti sono pronti l'**host avvia** la partita.

Dettagli tecnici:
- Ogni posto umano riceve un **token segreto**; il server valida che ogni azione arrivi dal giocatore di turno (header `X-Player-Token`).
- Lo stato è sincronizzato in tempo reale via **WebSocket** (`/ws/{game_id}`); la lobby usa `/ws/lobby/{lobby_id}`.
- L'**host guida i turni delle CPU**; le partite locali (hot-seat) restano invariate e senza enforcement.

## 📸 Screenshots

_Screenshot in arrivo (menù principale, lobby online, partita in corso). Le immagini vanno in `docs/screenshots/`._

<!-- Scommentare quando le immagini sono presenti in docs/screenshots/:
| Menù principale | Lobby online | Partita in corso |
|---|---|---|
| ![Menu](docs/screenshots/menu.png) | ![Lobby](docs/screenshots/lobby.png) | ![Gioco](docs/screenshots/game.png) |
-->

### Deploy Raspberry Pi 4

Gira come servizio systemd su porta 8081 con ottimizzazioni per ARM64:

- **GZip middleware** — SVG 506KB → ~60KB, JS 73KB → ~20KB
- **Cache headers** — asset statici cachati 24h
- **Monte Carlo 100 iterazioni** — probabilità attacco 5× più veloce
- **AI in asyncio.to_thread** — non blocca WebSocket durante turni CPU

## 📁 Struttura

```
RISIKO/
├── run.sh                    # Avvia il server
├── requirements.txt          # fastapi, uvicorn, websockets, pydantic
├── server/
│   ├── main.py              # FastAPI REST + WebSocket API
│   ├── game_engine.py       # Logica di gioco completa
│   ├── map_data.py          # 42 territori, 6 continenti, adiacenze
│   ├── models.py            # Pydantic models
│   ├── combat.py            # Dadi + probabilità attacco (Monte Carlo)
│   ├── cards.py             # Mazzo 44 carte + tris
│   ├── objectives.py        # 14 obiettivi segreti ufficiali
│   └── ai_player.py         # AI con difficoltà e personalità
├── client/
│   ├── index.html           # Layout RisikoPlay-style
│   ├── style.css            # Dark theme, animazioni
│   ├── app.js               # Logica UI completa
│   ├── sounds.js            # Effetti sonori Web Audio
│   ├── dice.js              # Animazione dadi
│   └── assets/world.svg     # Mappa mondo (da Wikipedia)
└── regolamento.pdf           # Regolamento ufficiale italiano
```

## 🎯 Regole implementate

- Piazzamento iniziale: 3 armate per turno, distribuibili su territori diversi
- Rinforzi: territori÷3 (min 3) + bonus continenti + tris carte
- Attacco: 1-3 dadi attaccante, 1-3 dadi difensore, parità → vince difensore
- Carte: 3 cannoni=4, 3 fanti=6, 3 cavalieri=8, misto=10, jolly+2=12, +2 per territorio posseduto
- Spostamento strategico: tra territori connessi (catena di territori propri)
- Obiettivi: 6 combinazioni continenti + 2 conteggio + 6 "distruggi colore"
- Obbligo scambio carte con 5+ in mano

## ⌨️ Scorciatoie

| Tasto | Azione |
|-------|--------|
| R | Reset selezione |
| Spazio | Fine turno |
| Esc | Annulla |
| Doppio click | Attacco rapido su nemico |
| Ctrl+Drag | Pan mappa |
| Scroll | Zoom mappa |

## 🤖 AI

L'AI ha 3 livelli di difficoltà (Facile/Medio/Difficile) e 3 personalità assegnate casualmente:
- **Aggressivo** — attacca spesso, anche con poco vantaggio
- **Difensivo** — fortifica molto, attacca solo con grande vantaggio
- **Espansionista** — punta a completare continenti

## 📜 Licenza

MIT
