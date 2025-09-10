import copy
import json
import base64
from datetime import date, timedelta
import re

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


def test_webhook_updates_fecha_cliente(monkeypatch):
    projects = [
        {
            "id": "p1",
            "name": "Proj1",
            "client": "ClientX",
            "source": "api",
            "phases": {},
            "assigned": {},
            "auto_hours": {},
            "kanban_id": "10",
            "due_date": "2024-05-10",
            "color": "#ffffff",
            "due_confirmed": False,
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
                "customFields": {"Fecha Cliente": "10/05/2024"},
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
            "customFields": {"Fecha Cliente": "11/05/2024"},
        },
        "timestamp": "t1",
    }
    response = client.post("/kanbanize-webhook", json=payload)

    assert response.status_code == 200
    assert projects[0]["due_date"] == date(2024, 5, 11).isoformat()
    assert len(saved) == 1


def test_webhook_creates_mecanizado_tratamiento(monkeypatch):
    projects = [
        {
            "id": "p1",
            "name": "Proj1",
            "client": "ClientX",
            "source": "api",
            "phases": {},
            "assigned": {},
            "auto_hours": {},
            "kanban_id": "10",
            "due_date": "",
            "color": "#ffffff",
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
                "customFields": {},
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
            "customFields": {"MECANIZADO": "sí", "TRATAMIENTO": "sí"},
        },
        "timestamp": "t1",
    }
    response = client.post("/kanbanize-webhook", json=payload)

    assert response.status_code == 200
    assert projects[0]["phases"]["mecanizar"] == 1
    assert projects[0]["phases"]["tratamiento"] == 1
    assert projects[0]["assigned"]["mecanizar"] == app.UNPLANNED
    assert projects[0]["assigned"]["tratamiento"] == app.UNPLANNED
    assert projects[0]["auto_hours"]["mecanizar"] is True
    assert projects[0]["auto_hours"]["tratamiento"] is True
    assert saved


def test_webhook_preserves_existing_mecanizado_tratamiento(monkeypatch):
    projects = [
        {
            "id": "p1",
            "name": "Proj1",
            "client": "ClientX",
            "source": "api",
            "phases": {"mecanizar": 5, "tratamiento": 2},
            "assigned": {"mecanizar": app.UNPLANNED, "tratamiento": app.UNPLANNED},
            "auto_hours": {},
            "kanban_id": "10",
            "due_date": "",
            "color": "#ffffff",
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
                "customFields": {},
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
            "customFields": {"MECANIZADO": "sí", "TRATAMIENTO": "sí"},
        },
        "timestamp": "t1",
    }
    response = client.post("/kanbanize-webhook", json=payload)

    assert response.status_code == 200
    assert projects[0]["phases"]["mecanizar"] == 5
    assert projects[0]["phases"]["tratamiento"] == 2
    assert "mecanizar" not in projects[0]["auto_hours"]
    assert "tratamiento" not in projects[0]["auto_hours"]
    assert saved == []

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


def test_pedido_title_date_persistence(monkeypatch):
    today = date.today()
    first_day = date(today.year, today.month, 1)
    while first_day.weekday() >= 5:
        first_day += timedelta(days=1)
    second_day = first_day + timedelta(days=1)
    while second_day.weekday() >= 5:
        second_day += timedelta(days=1)
    d1_day = first_day.day
    d2_day = second_day.day
    month_str = f"{today.month:02d}"
    card_store = []

    monkeypatch.setattr(app, "load_kanban_cards", lambda: list(card_store))

    def fake_save_cards(cards):
        card_store[:] = cards

    monkeypatch.setattr(app, "save_kanban_cards", fake_save_cards)
    monkeypatch.setattr(app, "load_column_colors", lambda: {})
    monkeypatch.setattr(app, "save_column_colors", lambda data: None)

    client = app.app.test_client()

    payload1 = {
        "card": {
            "taskid": 1,
            "laneName": "Seguimiento compras",
            "columnName": "Laser",
            "title": f"Pedido ({d1_day:02d}/{month_str})",
            "deadline": today.isoformat(),
        },
        "timestamp": "t1",
    }
    client.post("/kanbanize-webhook", json=payload1)
    assert card_store[0]["stored_title_date"] == f"{d1_day:02d}/{month_str}"

    payload2 = {
        "card": {
            "taskid": 1,
            "laneName": "Seguimiento compras",
            "columnName": "Laser",
            "title": "Pedido sin fecha",
            "deadline": today.isoformat(),
        },
        "timestamp": "t2",
    }
    client.post("/kanbanize-webhook", json=payload2)
    assert card_store[0]["stored_title_date"] == f"{d1_day:02d}/{month_str}"

    auth = {"Authorization": "Basic " + base64.b64encode(b"admin:secreto").decode()}
    resp = client.get("/calendario-pedidos", headers=auth)
    text = resp.get_data(as_text=True)
    d1 = date(today.year, today.month, d1_day).isoformat()
    assert re.search(rf'<td data-date="{d1}".*?Pedido sin fecha', text, re.S)

    payload3 = {
        "card": {
            "taskid": 1,
            "laneName": "Seguimiento compras",
            "columnName": "Laser",
            "title": f"Pedido ({d2_day:02d}/{month_str})",
            "deadline": today.isoformat(),
        },
        "timestamp": "t3",
    }
    client.post("/kanbanize-webhook", json=payload3)
    assert card_store[0]["stored_title_date"] == f"{d2_day:02d}/{month_str}"

    resp = client.get("/calendario-pedidos", headers=auth)
    text = resp.get_data(as_text=True)
    d2 = date(today.year, today.month, d2_day).isoformat()
    assert re.search(rf'<td data-date="{d2}".*?Pedido \({d2_day:02d}/{month_str}\)', text, re.S)


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


def test_move_phase_reverts_when_day_full(monkeypatch):
    projects = [
        {
            "id": "p1",
            "name": "Proj1",
            "client": "C1",
            "start_date": "2024-05-06",
            "due_date": "",
            "phases": {"montar": 8},
            "assigned": {"montar": "Mikel"},
            "auto_hours": {},
            "color": "#ffffff",
        },
        {
            "id": "p2",
            "name": "Proj2",
            "client": "C2",
            "start_date": "2024-05-07",
            "due_date": "",
            "phases": {"montar": 4},
            "assigned": {"montar": "Mikel"},
            "auto_hours": {},
            "color": "#ffffff",
        },
    ]

    monkeypatch.setattr(app, "load_projects", lambda: projects)

    def fake_save(projs):
        projects[:] = copy.deepcopy(projs)

    monkeypatch.setattr(app, "save_projects", fake_save)

    client = app.app.test_client()
    auth = {"Authorization": "Basic " + base64.b64encode(b"admin:secreto").decode()}
    resp = client.post(
        "/move",
        json={"pid": "p2", "phase": "montar", "date": "2024-05-06", "worker": "Mikel"},
        headers=auth,
    )

    assert resp.status_code == 409
    mapping = app.compute_schedule_map(projects)
    days = [d for _, d, ph, *_ in mapping["p2"] if ph == "montar"]
    assert days == ["2024-05-07"]


def test_gantt_view(monkeypatch):
    projects = [
        {
            "id": "p1",
            "name": "Proj1",
            "client": "Client1",
            "phases": {"montar": 8},
            "assigned": {"montar": "Mikel"},
            "color": "#123456",
        }
    ]
    fake_sched = {
        "Mikel": {
            "2024-01-01": [
                    {
                        "pid": "p1",
                        "phase": "montar",
                        "hours": 8,
                        "start_time": "2024-01-01T08:00:00",
                        "end_time": "2024-01-01T16:00:00",
                        "color": "#123456",
                        "worker": "Mikel",
                    }
                ]
            }
        }
    monkeypatch.setattr(app, "load_projects", lambda: copy.deepcopy(projects))
    monkeypatch.setattr(app, "schedule_projects", lambda projs: (fake_sched, []))
    client = app.app.test_client()
    auth = {"Authorization": "Basic " + base64.b64encode(b"admin:secreto").decode()}
    resp = client.get("/gantt", headers=auth)
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Proj1" in body
    assert "Client1" in body
    assert "montar" in body
    assert '"worker": "Mikel"' in body
    assert "Resumen" in body
    assert "2024-01-01" in body
    # color and bar size indicators
    assert "#123456" in body
    assert "BAR_HEIGHT = 60" in body
    assert "overflow-x:auto" in body
    assert "overflow-y:hidden" in body
    assert "overflow:visible" in body
    assert "addEventListener('wheel'" in body

