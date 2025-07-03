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

function openNewModal(parentId = null) {
    const form = document.getElementById('cardForm');
    form.action = '/add_card';
    document.getElementById('cardModalLabel').textContent = 'Nueva tarjeta';
    form.reset();
    document.getElementById('parent_id').value = parentId || '';
    var modal = bootstrap.Modal.getOrCreateInstance(document.getElementById('cardModal'));
    modal.show();
}

function openEditModal(id) {
    fetch(`/card/${id}`).then(r => r.json()).then(data => {
        const form = document.getElementById('cardForm');
        form.action = `/card/${id}`;
        document.getElementById('cardModalLabel').textContent = 'Editar tarjeta';
        document.getElementById('title').value = data.title;
        document.getElementById('description').value = data.description || '';
        document.getElementById('assignee').value = data.assignee || '';
        document.getElementById('due_date').value = data.due_date || '';
        document.getElementById('column_id').value = data.column_id;
        document.getElementById('parent_id').value = data.parent_id || '';
        var modal = bootstrap.Modal.getOrCreateInstance(document.getElementById('cardModal'));
        modal.show();
    });
}

