/**
 * RISIKO — Sound effects using Web Audio API (no external files needed)
 */

const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
let soundEnabled = true;

function playClick() {
    if (!soundEnabled) return;
    const o = audioCtx.createOscillator();
    const g = audioCtx.createGain();
    o.connect(g); g.connect(audioCtx.destination);
    o.frequency.value = 600;
    g.gain.setValueAtTime(0.15, audioCtx.currentTime);
    g.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.1);
    o.start(); o.stop(audioCtx.currentTime + 0.1);
}

function playDice() {
    if (!soundEnabled) return;
    for (let i = 0; i < 4; i++) {
        setTimeout(() => {
            const o = audioCtx.createOscillator();
            const g = audioCtx.createGain();
            o.connect(g); g.connect(audioCtx.destination);
            o.type = 'square';
            o.frequency.value = 200 + Math.random() * 400;
            g.gain.setValueAtTime(0.08, audioCtx.currentTime);
            g.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.06);
            o.start(); o.stop(audioCtx.currentTime + 0.06);
        }, i * 50);
    }
}

function playConquest() {
    if (!soundEnabled) return;
    const notes = [523, 659, 784]; // C5, E5, G5
    notes.forEach((freq, i) => {
        setTimeout(() => {
            const o = audioCtx.createOscillator();
            const g = audioCtx.createGain();
            o.connect(g); g.connect(audioCtx.destination);
            o.type = 'triangle';
            o.frequency.value = freq;
            g.gain.setValueAtTime(0.2, audioCtx.currentTime);
            g.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.25);
            o.start(); o.stop(audioCtx.currentTime + 0.25);
        }, i * 120);
    });
}

function playVictory() {
    if (!soundEnabled) return;
    const melody = [523, 659, 784, 1047, 784, 1047]; // Fanfare
    melody.forEach((freq, i) => {
        setTimeout(() => {
            const o = audioCtx.createOscillator();
            const g = audioCtx.createGain();
            o.connect(g); g.connect(audioCtx.destination);
            o.type = 'triangle';
            o.frequency.value = freq;
            g.gain.setValueAtTime(0.25, audioCtx.currentTime);
            g.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.3);
            o.start(); o.stop(audioCtx.currentTime + 0.3);
        }, i * 150);
    });
}

function toggleSound() {
    soundEnabled = !soundEnabled;
    return soundEnabled;
}
