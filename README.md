# ⚔️ RISIKO — Web Game

Un clone completo del gioco da tavolo **RisiKo!** giocabile nel browser, con AI avversaria e regole ufficiali italiane.

![Python](https://img.shields.io/badge/Python-3.12-blue) ![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green) ![License](https://img.shields.io/badge/License-MIT-yellow)

## 🎮 Features

- **Mappa mondo interattiva** — SVG da Wikipedia con 42 territori cliccabili, zoom/pan
- **Regole ufficiali italiane** — difensore 3 dadi, tris carte (4/6/8/10/12), obiettivi segreti, spostamento tra territori connessi
- **AI con personalità** — 3 livelli di difficoltà × 3 personalità (aggressivo, difensivo, espansionista) + trash talk
- **3-6 giocatori** — umani e/o CPU, hot-seat
- **Lancia i dadi di difesa** — quando l'AI ti attacca, sei TU a premere il pulsante
- **Interfaccia stile RisikoPlay** — mappa fullscreen, pannelli overlay, frecce attacco animate
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
