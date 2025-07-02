let draggedCard = null;

function dragstart_handler(ev) {
    draggedCard = ev.target;
    ev.dataTransfer.effectAllowed = 'move';
}

function dragover_handler(ev) {
    ev.preventDefault();
    ev.dataTransfer.dropEffect = 'move';
}

function drop_handler(ev) {
    ev.preventDefault();
    if (draggedCard) {
        let column = ev.currentTarget.closest('.kanban-column');
        column.querySelector('.kanban-cards').appendChild(draggedCard);
        updatePosition(draggedCard.dataset.cardId, column.dataset.colId);
    }
}

function updatePosition(cardId, columnId) {
    const columnCards = document.querySelectorAll(`.kanban-column[data-col-id="${columnId}"] .kanban-card`);
    columnCards.forEach((card, index) => {
        fetch('/move_card', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ card_id: card.dataset.cardId, column_id: columnId, position: index })
        });
    });
}
