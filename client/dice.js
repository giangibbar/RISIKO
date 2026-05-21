/**
 * RISIKO — Dice animation module
 */

const DICE_FACES = ['⚀', '⚁', '⚂', '⚃', '⚄', '⚅'];

function animateDice(attackerDice, defenderDice) {
    const display = document.getElementById('dice-display');

    // Start with random faces spinning
    let frames = 8;
    let frame = 0;

    function renderFrame() {
        const attHtml = attackerDice.map(() =>
            `<div class="die rolling">${DICE_FACES[Math.floor(Math.random() * 6)]}</div>`
        ).join('');
        const defHtml = defenderDice.map(() =>
            `<div class="die rolling">${DICE_FACES[Math.floor(Math.random() * 6)]}</div>`
        ).join('');

        display.innerHTML = `
            <div class="dice-group attacker">${attHtml}</div>
            <span class="vs-label">VS</span>
            <div class="dice-group defender">${defHtml}</div>
        `;

        frame++;
        if (frame < frames) {
            setTimeout(renderFrame, 80);
        } else {
            // Show final result
            renderFinalDice(attackerDice, defenderDice);
        }
    }

    renderFrame();
}

function renderFinalDice(attackerDice, defenderDice) {
    const display = document.getElementById('dice-display');

    const attHtml = attackerDice.map(d =>
        `<div class="die">${DICE_FACES[d - 1]}</div>`
    ).join('');
    const defHtml = defenderDice.map(d =>
        `<div class="die">${DICE_FACES[d - 1]}</div>`
    ).join('');

    display.innerHTML = `
        <div class="dice-group attacker">${attHtml}</div>
        <span class="vs-label">VS</span>
        <div class="dice-group defender">${defHtml}</div>
    `;
}
