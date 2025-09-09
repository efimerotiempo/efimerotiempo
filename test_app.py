import copy
import json
import base64
from datetime import date

import pytest

import app


def test_last_kanban_card(monkeypatch):
    sample = [
        {"timestamp": 1, "card": {"taskid": "1", "value": "a"}},
        {"timestamp": 2, "card": {"cardId": "2", "value": "b"}},
        {"timestamp": 3, "card": {"taskid": "1", "value": "c"}},
    ]
    monkeypatch.setattr(app, "load_kanban_cards", lambda: sample)

    assert app.last_kanban_card("1") == {"taskid": "1", "value": "c"}
    assert app.last_kanban_card("2") == {"cardId": "2", "value": "b"}
    assert app.last_kanban_card("3") == {}


def test_webhook_updates_only_changed_fields(monkeypatch):
    projects = [
        {
            "id": "p1",
            "name": "Proj1",
            "client": "ClientX",
            "source": "api",
            "phases": {"recepcionar material": 5},
            "assigned": {"recepcionar material": "Pilar"},
            "auto_hours": {},
            "kanban_id": "10",
            "due_date": "2024-05-10",
            "material_confirmed_date": "",
            "color": "#ffffff",
            "due_confirmed": True,
            "due_warning": True,
        }
    ]
    saved = []

    monkeypatch.setattr(app, "load_projects", lambda: projects)

    def fake_save(projs):
        saved.append(copy.deepcopy(projs))

    monkeypatch.setattr(app, "save_projects", fake_save)

    prev_cards = [
        {
            "timestamp": "t0",
            "card": {
                "taskid": "10",
                "customCardId": "Proj1",
                "title": "ClientX",
                "customFields": {"Horas Preparación": "5"},
                "deadline": "2024-05-10",
            },
        }
    ]
    card_store = list(prev_cards)
    monkeypatch.setattr(app, "load_kanban_cards", lambda: list(card_store))

    def fake_save_cards(cards):
        card_store[:] = cards

    monkeypatch.setattr(app, "save_kanban_cards", fake_save_cards)

    client = app.app.test_client()
    payload = {
        "card": {
            "taskid": "10",
            "laneName": "Acero al Carbono",
            "columnName": "Planif. Bekola",
            "customCardId": "Proj1",
            "title": "ClientX",
            "customFields": {"Horas Preparación": "7"},
            "deadline": "2024-05-10",
        },
        "timestamp": "t1",
    }
    response = client.post("/kanbanize-webhook", json=payload)

    assert response.status_code == 200
    assert projects[0]["phases"]["recepcionar material"] == 7
    assert projects[0]["client"] == "ClientX"
    assert projects[0]["due_date"] == "2024-05-10"
    assert projects[0]["assigned"]["recepcionar material"] == "Pilar"
    assert len(saved) == 1


def test_title_update_replaces_old_pedido(monkeypatch):
    today = date.today()
    card_store = [
        {
            "timestamp": "t0",
            "card": {
                "taskid": 1,
                "lanename": "Seguimiento compras",
                "columnname": "Laser",
                "title": "Old",
                "deadline": today.isoformat(),
            },
        }
    ]

    monkeypatch.setattr(app, "load_kanban_cards", lambda: list(card_store))

    def fake_save_cards(cards):
        card_store[:] = cards

    monkeypatch.setattr(app, "save_kanban_cards", fake_save_cards)
    monkeypatch.setattr(app, "load_column_colors", lambda: {})
    monkeypatch.setattr(app, "save_column_colors", lambda data: None)

    client = app.app.test_client()
    payload = {
        "card": {
            "taskid": 1,
            "laneName": "Seguimiento compras",
            "columnName": "Laser",
            "title": "New",
            "deadline": today.isoformat(),
        },
        "timestamp": "t1",
    }
    response = client.post("/kanbanize-webhook", json=payload)

    assert response.status_code == 200
    assert len(card_store) == 1
    assert card_store[0]["card"]["title"] == "New"

    auth = {"Authorization": "Basic " + base64.b64encode(b"admin:secreto").decode()}
    resp = client.get("/calendario-pedidos", headers=auth)
    text = resp.get_data(as_text=True)
    assert "New" in text
    assert "Old" not in text


def test_unfreeze_preserves_displaced_phase(monkeypatch):
    projects = [
        {
            "id": "p1",
            "name": "P1",
            "client": "C1",
            "start_date": "2024-01-01",
            "due_date": "",
            "phases": {"montar": 8},
            "assigned": {"montar": "Mikel"},
            "auto_hours": {},
            "color": "#ffffff",
        },
        {
            "id": "p2",
            "name": "P2",
            "client": "C2",
            "start_date": "2024-01-01",
            "due_date": "",
            "phases": {"montar": 8},
            "assigned": {"montar": "Mikel"},
            "auto_hours": {},
            "color": "#ffffff",
        },
    ]
    saved = []

    monkeypatch.setattr(app, "load_projects", lambda: projects)
    monkeypatch.setattr(app, "save_projects", lambda p: saved.append(copy.deepcopy(p)))

    client = app.app.test_client()

    auth = {
        "Authorization": "Basic " + base64.b64encode(b"admin:secreto").decode()
    }

    client.post("/toggle_freeze/p2/montar", headers=auth)

    projects[0]["start_date"] = "2024-01-02"

    client.post("/toggle_freeze/p2/montar", headers=auth)

    mapping = app.compute_schedule_map(projects)
    p1_day = [d for w, d, ph, *_ in mapping["p1"] if ph == "montar"][0]

    assert p1_day == "2024-01-03"
    assert projects[0]["segment_starts"]["montar"][0] == "2024-01-03"


def test_frozen_phase_stays_in_cell_and_respects_start_order():
    projects = [
        {
            "id": "p1",
            "name": "P1",
            "client": "C",
            "start_date": "2024-01-01",
            "due_date": "",
            "phases": {"dibujo": 4},
            "assigned": {"dibujo": "Mikel"},
            "auto_hours": {},
            "color": "#ffffff",
            "frozen_tasks": [
                {
                    "phase": "dibujo",
                    "hours": 4,
                    "start": 4,
                    "worker": "Mikel",
                    "day": "2024-01-02",
                    "project": "P1",
                    "client": "C",
                    "color": "#ffffff",
                    "due_date": "",
                    "start_date": "2024-01-01",
                    "pid": "p1",
                    "frozen": True,
                }
            ],
        },
        {
            "id": "p2",
            "name": "P2",
            "client": "C",
            "start_date": "2024-01-02",
            "due_date": "",
            "phases": {"dibujo": 4},
            "assigned": {"dibujo": "Mikel"},
            "auto_hours": {},
            "color": "#ffffff",
        },
    ]
    schedule, _ = app.schedule_projects(projects)
    tasks = schedule["Mikel"]["2024-01-02"]
    assert [t["pid"] for t in tasks] == ["p2", "p1"]
    assert [t["start"] for t in tasks] == [0, 4]
    assert tasks[1].get("frozen")

