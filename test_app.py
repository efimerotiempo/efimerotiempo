import copy
import json
import base64
from datetime import date, timedelta, datetime
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
    monkeypatch.setattr(app, "_fetch_kanban_card", lambda cid, with_links=False, card=payload["card"]: card)
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
    monkeypatch.setattr(app, "_fetch_kanban_card", lambda cid, with_links=False, card=payload["card"]: card)
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
    monkeypatch.setattr(app, "_fetch_kanban_card", lambda cid, with_links=False, card=payload["card"]: card)
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
    monkeypatch.setattr(app, "_fetch_kanban_card", lambda cid, with_links=False, card=payload["card"]: card)
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
    monkeypatch.setattr(app, "_fetch_kanban_card", lambda cid, with_links=False, card=payload["card"]: card)
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

    current_payload = {}
    def fake_fetch(cid, with_links=False):
        return current_payload.get("card", {"taskid": cid})

    monkeypatch.setattr(app, "_fetch_kanban_card", fake_fetch)

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
    current_payload = payload1
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
    current_payload = payload2
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
    current_payload = payload3
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
            "due_date": "2024-02-01",
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
    assert '"due_date": "2024-02-01"' in body
    assert "sort_start" in body
    assert "sort_due" in body
    # color and bar size indicators
    assert "#123456" in body
    assert "BAR_HEIGHT = 30" in body
    assert ".gantt-row { height:29px" in body
    assert "overflow-x:auto" in body
    assert "overflow-y:auto" in body
    assert "overflow:visible" in body
    assert "gantt-main::-webkit-scrollbar" in body
    assert "scrollbar-width:none" in body
    assert "syncScroll(main, summaryContainer)" in body
    assert "syncScroll(summaryContainer, main)" in body
    assert "height:80vh" in body
    # days scaled to the workday duration
    assert "startOfDay" in body
    assert "+ 1)*pxPerDay" in body


def test_delete_project_cleans_conflicts(monkeypatch):
    today = date.today().isoformat()
    projects = [
        {"id": "p1", "name": "Proj1", "client": "C1", "phases": {}, "start_date": today},
        {"id": "p2", "name": "Proj2", "client": "C2", "phases": {}, "start_date": today},
    ]
    extras_store = [
        {"id": "1", "project": "Proj1", "client": "C1", "message": "x", "key": "k1", "pid": "p1"},
        {"id": "2", "project": "Proj2", "client": "C2", "message": "y", "key": "k2", "pid": "p2"},
    ]
    dismissed_store = [
        "Proj1|No se cumple la fecha de entrega",
        "Proj2|No se cumple la fecha de entrega",
        "kanban-p1",
        "kanban-p2",
    ]

    monkeypatch.setattr(app, "compute_schedule_map", lambda projs: {})
    monkeypatch.setattr(app, "save_projects", lambda projs: None)
    monkeypatch.setattr(app, "load_extra_conflicts", lambda: list(extras_store))

    def fake_save_extra(data):
        extras_store[:] = data

    monkeypatch.setattr(app, "save_extra_conflicts", fake_save_extra)
    monkeypatch.setattr(app, "load_dismissed", lambda: list(dismissed_store))

    def fake_save_dismissed(data):
        dismissed_store[:] = data

    monkeypatch.setattr(app, "save_dismissed", fake_save_dismissed)

    app.remove_project_and_preserve_schedule(projects, "p1")

    assert all(c.get("pid") != "p1" for c in extras_store)
    assert all("Proj1|" not in k and k != "kanban-p1" for k in dismissed_store)


def test_calendar_pedidos_includes_child_links(monkeypatch):
    cards = [
        {
            "card": {
                "taskid": "1",
                "title": "ProjA - Client1",
                "columnname": "Administración",
                "lanename": "Acero al Carbono",
            }
        },
        {
            "card": {
                "taskid": "2",
                "title": "Child1",
                "columnname": "X",
                "lanename": "Seguimiento compras",
                "links": {"parent": [{"taskid": "1"}]},
            }
        },
    ]
    monkeypatch.setattr(app, "load_kanban_cards", lambda: cards)
    monkeypatch.setattr(app, "load_column_colors", lambda: {"Administración": "#111", "X": "#222"})
    monkeypatch.setattr(app, "save_column_colors", lambda c: None)

    client = app.app.test_client()
    auth = {"Authorization": "Basic " + base64.b64encode(b"admin:secreto").decode()}
    resp = client.get("/calendario-pedidos", headers=auth)
    html = resp.get_data(as_text=True)

    import re
    row_pattern = re.compile(
        r'<div class="project-row"[^>]*>[\s\S]*?ProjA[\s\S]*?Child1[\s\S]*?</div>',
        re.MULTILINE,
    )
    assert row_pattern.search(html)


def test_project_links_endpoint(monkeypatch):
    cards = [
        {
            "card": {
                "taskid": "1",
                "title": "ProjA - Client1",
                "columnname": "Administración",
                "lanename": "Acero al Carbono",
            }
        },
        {
            "card": {
                "taskid": "2",
                "title": "Child1",
                "columnname": "X",
                "lanename": "Seguimiento compras",
                "links": {"parent": [{"taskid": "1"}]},
            }
        },
    ]
    monkeypatch.setattr(app, "load_kanban_cards", lambda: cards)
    monkeypatch.setattr(app, "load_column_colors", lambda: {"Administración": "#111", "X": "#222"})
    monkeypatch.setattr(app, "save_column_colors", lambda c: None)

    client = app.app.test_client()
    auth = {"Authorization": "Basic " + base64.b64encode(b"admin:secreto").decode()}
    resp = client.get("/project_links", headers=auth)
    assert resp.get_json() == [
        {"project": "ProjA", "client": "Client1", "links": ["Child1"]}
    ]


def test_project_links_omit_projects_without_children(monkeypatch):
    cards = [
        {
            "card": {
                "taskid": "1",
                "title": "ProjA - Client1",
                "columnname": "Administración",
                "lanename": "Acero al Carbono",
            }
        }
    ]
    monkeypatch.setattr(app, "load_kanban_cards", lambda: cards)
    monkeypatch.setattr(app, "load_column_colors", lambda: {"Administración": "#111"})
    monkeypatch.setattr(app, "save_column_colors", lambda c: None)

    client = app.app.test_client()
    auth = {"Authorization": "Basic " + base64.b64encode(b"admin:secreto").decode()}

    resp = client.get("/project_links", headers=auth)
    assert resp.get_json() == []

    resp = client.get("/calendario-pedidos", headers=auth)
    html = resp.get_data(as_text=True)
    assert "ProjA" not in html


def test_calendar_pedidos_child_links_from_parent(monkeypatch):
    cards = [
        {
            "card": {
                "taskid": "1",
                "title": "ProjA - Client1",
                "columnname": "Administración",
                "lanename": "Acero al Carbono",
                "links": {"child": [{"taskid": "2"}]},
            }
        }
    ]
    monkeypatch.setattr(app, "load_kanban_cards", lambda: cards)
    monkeypatch.setattr(app, "load_column_colors", lambda: {"Administración": "#111"})
    monkeypatch.setattr(app, "save_column_colors", lambda c: None)
    monkeypatch.setattr(app, "_fetch_kanban_card", lambda cid: {"title": "Child1"} if cid == "2" else None)

    client = app.app.test_client()
    auth = {"Authorization": "Basic " + base64.b64encode(b"admin:secreto").decode()}
    resp = client.get("/calendario-pedidos", headers=auth)
    html = resp.get_data(as_text=True)
    assert "Child1" in html


def test_calendar_pedidos_limits_past_weeks(monkeypatch):
    class FakeDate(date):
        @classmethod
        def today(cls):
            return date(2024, 6, 19)

        @classmethod
        def fromisoformat(cls, s):
            return date.fromisoformat(s)

    monkeypatch.setattr(app, "date", FakeDate)

    compras = {
        "1": {
            "card": {
                "taskid": "1",
                "title": "T1",
                "columnname": "Plegado/Curvado",
                "lanename": "Seguimiento compras",
                "deadline": "2024-05-01",
            }
        },
        "2": {
            "card": {
                "taskid": "2",
                "title": "T2",
                "columnname": "Plegado/Curvado",
                "lanename": "Seguimiento compras",
                "deadline": "2024-05-30",
            }
        },
    }

    monkeypatch.setattr(
        app, "load_compras_raw", lambda: (compras, {"Plegado/Curvado": "#111"})
    )
    monkeypatch.setattr(app, "build_project_links", lambda cr: [])

    client = app.app.test_client()
    auth = {"Authorization": "Basic " + base64.b64encode(b"admin:secreto").decode()}
    resp = client.get("/calendario-pedidos", headers=auth)
    html = resp.get_data(as_text=True)

    assert 'data-date="2024-05-27"' in html
    assert 'data-date="2024-05-20"' not in html
    assert re.search(r'data-date="2024-05-27"[\s\S]*T1', html)
    assert re.search(r'data-date="2024-05-30"[\s\S]*T2', html)


def test_webhook_enriches_child_links(monkeypatch):
    card_store = [
        {
            "timestamp": "t0",
            "card": {
                "taskid": "1",
                "title": "ProjA - Client1",
                "columnname": "Administración",
                "lanename": "Acero al Carbono",
            },
        }
    ]
    monkeypatch.setattr(app, "load_kanban_cards", lambda: list(card_store))

    def fake_save(cards):
        card_store[:] = cards

    monkeypatch.setattr(app, "save_kanban_cards", fake_save)

    enriched = {
        "taskid": "2",
        "title": "Child1",
        "columnname": "X",
        "lanename": "Seguimiento compras",
        "links": {"parent": [{"taskid": "1"}]},
    }
    monkeypatch.setattr(app, "_fetch_kanban_card", lambda cid, with_links=False: enriched)

    client = app.app.test_client()
    payload = {
        "card": {
            "taskid": "2",
            "laneName": "Seguimiento compras",
            "columnName": "X",
            "title": "Child1",
        },
        "timestamp": "t1",
    }
    client.post("/kanbanize-webhook", json=payload)

    assert card_store[-1]["card"].get("links") == {"parent": [{"taskid": "1"}]}

    monkeypatch.setattr(app, "load_column_colors", lambda: {"Administración": "#111", "X": "#222"})
    monkeypatch.setattr(app, "save_column_colors", lambda c: None)
    auth = {"Authorization": "Basic " + base64.b64encode(b"admin:secreto").decode()}
    resp = client.get("/calendario-pedidos", headers=auth)
    html = resp.get_data(as_text=True)
    assert "Child1" in html


def test_webhook_triggers_broadcast(monkeypatch):
    events = []
    monkeypatch.setattr(app, "broadcast_event", lambda data: events.append(data))
    monkeypatch.setattr(app, "save_kanban_cards", lambda cards: None)
    monkeypatch.setattr(app, "load_kanban_cards", lambda: [])
    payload = {
        "card": {
            "taskid": "5",
            "laneName": "Seguimiento compras",
            "columnName": "X",
            "title": "Card5",
        },
        "timestamp": "t1",
    }
    monkeypatch.setattr(app, "_fetch_kanban_card", lambda cid, with_links=True, card=payload["card"]: card)
    client = app.app.test_client()
    resp = client.post("/kanbanize-webhook", json=payload)
    assert resp.status_code == 200
    assert events == [{"type": "kanban_update"}]


def test_update_worker_note(monkeypatch):
    store = {}
    monkeypatch.setattr(app, "load_worker_notes", lambda: store.copy())
    def fake_save(data):
        store.update(data)
    monkeypatch.setattr(app, "save_worker_notes", fake_save)
    fake_now = datetime(2025, 1, 2, 15, 30)
    class FakeDT(datetime):
        @classmethod
        def now(cls):
            return fake_now
        @classmethod
        def fromisoformat(cls, s):
            return datetime.fromisoformat(s)
    monkeypatch.setattr(app, "datetime", FakeDT)
    client = app.app.test_client()
    auth = {"Authorization": "Basic " + base64.b64encode(b"admin:secreto").decode()}
    resp = client.post("/update_worker_note", json={"worker": "Irene", "text": "Hola"}, headers=auth)
    assert resp.status_code == 200
    assert store["Irene"]["text"] == "Hola"
    assert store["Irene"]["edited"] == fake_now.isoformat(timespec="minutes")
    assert resp.get_json()["edited"] == "15:30 02/01"


def test_update_pedido_date(monkeypatch):
    store = [
        {
            "timestamp": "t0",
            "stored_title_date": "03/05",
            "card": {
                "taskid": "10",
                "title": "ProjA - Client1",
                "columnname": "Plegado/Curvado",
                "lanename": "Seguimiento compras",
                "deadline": "2025-05-03",
            },
        }
    ]
    monkeypatch.setattr(app, "load_kanban_cards", lambda: store)

    def fake_save(cards):
        store[:] = cards

    monkeypatch.setattr(app, "save_kanban_cards", fake_save)
    monkeypatch.setattr(app, "broadcast_event", lambda data: None)
    monkeypatch.setattr(app, "load_column_colors", lambda: {"Plegado/Curvado": "#111"})
    monkeypatch.setattr(app, "save_column_colors", lambda c: None)

    class FakeDate(date):
        @classmethod
        def today(cls):
            return date(2025, 5, 1)

        @classmethod
        def fromisoformat(cls, s):
            return date.fromisoformat(s)

    monkeypatch.setattr(app, "date", FakeDate)

    client = app.app.test_client()
    auth = {"Authorization": "Basic " + base64.b64encode(b"admin:secreto").decode()}
    resp = client.post(
        "/update_pedido_date",
        json={"cid": "10", "date": "2025-05-12"},
        headers=auth,
    )
    assert resp.status_code == 200
    assert store[0]["stored_title_date"] == "12/05"

    resp = client.get("/calendario-pedidos", headers=auth)
    html = resp.get_data(as_text=True)
    assert re.search(r'data-date="2025-05-12"[\s\S]*ProjA', html)


def test_move_pedido_to_unconfirmed_remembers_date(monkeypatch):
    store = [
        {
            "timestamp": "t0",
            "card": {
                "taskid": "20",
                "title": "ProjB - Client2",
                "columnname": "Planif. OTROS",
                "lanename": "Seguimiento compras",
                "deadline": "2025-07-10",
            },
        }
    ]
    monkeypatch.setattr(app, "load_kanban_cards", lambda: store)

    def fake_save(cards):
        store[:] = cards

    monkeypatch.setattr(app, "save_kanban_cards", fake_save)
    monkeypatch.setattr(app, "broadcast_event", lambda data: None)
    monkeypatch.setattr(app, "load_column_colors", lambda: {"Planif. OTROS": "#111"})
    monkeypatch.setattr(app, "save_column_colors", lambda c: None)

    class FakeDate(date):
        @classmethod
        def today(cls):
            return date(2025, 7, 1)

    monkeypatch.setattr(app, "date", FakeDate)

    client = app.app.test_client()
    auth = {"Authorization": "Basic " + base64.b64encode(b"admin:secreto").decode()}
    resp = client.post("/update_pedido_date", json={"cid": "20", "date": None}, headers=auth)
    assert resp.status_code == 200
    assert store[0].get("stored_title_date") is None
    assert store[0].get("previous_title_date") == "10/07"

    resp = client.get("/calendario-pedidos", headers=auth)
    html = resp.get_data(as_text=True)
    assert re.search(r'class="unconfirmed"[\s\S]*ProjB[\s\S]*10/07', html)


def test_move_pedido_from_calendar_to_unconfirmed_visible(monkeypatch):
    store = [
        {
            "timestamp": "t0",
            "card": {
                "taskid": "30",
                "title": "ProjC - Client3",
                "columnname": "Plegado/curvado - Fabricación",
                "lanename": "Seguimiento compras",
                "deadline": "2025-08-20",
            },
        }
    ]
    monkeypatch.setattr(app, "load_kanban_cards", lambda: store)

    def fake_save(cards):
        store[:] = cards

    monkeypatch.setattr(app, "save_kanban_cards", fake_save)
    monkeypatch.setattr(app, "broadcast_event", lambda data: None)
    monkeypatch.setattr(
        app, "load_column_colors", lambda: {"Plegado/curvado - Fabricación": "#111"}
    )
    monkeypatch.setattr(app, "save_column_colors", lambda c: None)

    class FakeDate(date):
        @classmethod
        def today(cls):
            return date(2025, 8, 1)

    monkeypatch.setattr(app, "date", FakeDate)

    client = app.app.test_client()
    auth = {"Authorization": "Basic " + base64.b64encode(b"admin:secreto").decode()}

    resp = client.post(
        "/update_pedido_date", json={"cid": "30", "date": None}, headers=auth
    )
    assert resp.status_code == 200
    assert store[0].get("previous_title_date") == "20/08"

    resp = client.get("/calendario-pedidos", headers=auth)
    html = resp.get_data(as_text=True)
    assert re.search(r'class="unconfirmed"[\s\S]*ProjC[\s\S]*20/08', html)


def test_unconfirmed_ignores_disallowed_columns(monkeypatch):
    store = [
        {
            "timestamp": "t0",
            "card": {
                "taskid": "40",
                "title": "ProjD - Client4",
                "columnname": "Random",
                "lanename": "Seguimiento compras",
                "deadline": "2025-09-15",
            },
        }
    ]
    monkeypatch.setattr(app, "load_kanban_cards", lambda: store)

    def fake_save(cards):
        store[:] = cards

    monkeypatch.setattr(app, "save_kanban_cards", fake_save)
    monkeypatch.setattr(app, "broadcast_event", lambda data: None)
    monkeypatch.setattr(app, "load_column_colors", lambda: {"Random": "#111"})
    monkeypatch.setattr(app, "save_column_colors", lambda c: None)

    class FakeDate(date):
        @classmethod
        def today(cls):
            return date(2025, 9, 1)

    monkeypatch.setattr(app, "date", FakeDate)

    client = app.app.test_client()
    auth = {"Authorization": "Basic " + base64.b64encode(b"admin:secreto").decode()}

    resp = client.post("/update_pedido_date", json={"cid": "40", "date": None}, headers=auth)
    assert resp.status_code == 200

    resp = client.get("/calendario-pedidos", headers=auth)
    html = resp.get_data(as_text=True)
    assert re.search(r'class="unconfirmed"[\s\S]*ProjD', html) is None


def test_calendar_renders_worker_note(monkeypatch):
    auth = {"Authorization": "Basic " + base64.b64encode(b"admin:secreto").decode()}
    monkeypatch.setattr(app, "get_projects", lambda: [])
    monkeypatch.setattr(app, "schedule_projects", lambda projects: ({"Irene": {}}, []))
    monkeypatch.setattr(app, "active_workers", lambda today=None: ["Irene"])
    monkeypatch.setattr(app, "load_notes", lambda: [])
    monkeypatch.setattr(app, "load_extra_conflicts", lambda: [])
    monkeypatch.setattr(app, "load_dismissed", lambda: [])
    monkeypatch.setattr(app, "load_daily_hours", lambda: {})
    monkeypatch.setattr(app, "load_worker_notes", lambda: {"Irene": {"text": "Nota", "edited": "2025-01-02T15:30"}})
    resp = app.app.test_client().get("/calendar", headers=auth)
    html = resp.get_data(as_text=True)
    assert "Nota" in html
    assert "15:30 02/01" in html


@pytest.mark.parametrize(
    "confirmed,expected",[(False, app.DEADLINE_MSG),(True, app.CLIENT_DEADLINE_MSG)]
)
def test_move_phase_warns_but_allows_plan(monkeypatch, confirmed, expected):
    projects = [{
        "id": "p1",
        "name": "Proj1",
        "client": "C1",
        "start_date": "2024-05-06",
        "due_date": "2024-05-10",
        "due_confirmed": confirmed,
        "phases": {"montar": 8},
        "assigned": {"montar": "Mikel"},
        "auto_hours": {},
        "color": "#fff",
    }]
    monkeypatch.setattr(app, "load_projects", lambda: projects)
    def fake_save(projs):
        projects[:] = copy.deepcopy(projs)
    monkeypatch.setattr(app, "save_projects", fake_save)
    client = app.app.test_client()
    auth = {"Authorization": "Basic " + base64.b64encode(b"admin:secreto").decode()}
    resp = client.post(
        "/move",
        json={"pid": "p1", "phase": "montar", "date": "2024-05-13", "worker": "Mikel"},
        headers=auth,
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["warning"].startswith(expected)
    assert projects[0]["segment_starts"]["montar"][0] == "2024-05-13"


def test_modals_escape_and_reload(monkeypatch):
    auth = {"Authorization": "Basic " + base64.b64encode(b"admin:secreto").decode()}
    monkeypatch.setattr(app, "get_projects", lambda: [])
    monkeypatch.setattr(app, "schedule_projects", lambda projects: ({"Irene": {}}, []))
    monkeypatch.setattr(app, "active_workers", lambda today=None: ["Irene"])
    monkeypatch.setattr(app, "load_notes", lambda: [])
    monkeypatch.setattr(app, "load_extra_conflicts", lambda: [])
    monkeypatch.setattr(app, "load_dismissed", lambda: [])
    monkeypatch.setattr(app, "load_daily_hours", lambda: {})
    monkeypatch.setattr(app, "load_worker_notes", lambda: {})

    client = app.app.test_client()
    html = client.get("/calendar", headers=auth).get_data(as_text=True)
    assert "e.key === 'Escape'" in html
    assert "showDeadline(data.warning, () => location.reload())" not in html

    html2 = client.get("/complete", headers=auth).get_data(as_text=True)
    assert "e.key === 'Escape'" in html2
    assert "showDeadline(data.warning, () => location.reload())" not in html2


def test_freeze_no_reload(monkeypatch):
    auth = {"Authorization": "Basic " + base64.b64encode(b"admin:secreto").decode()}
    monkeypatch.setattr(app, "get_projects", lambda: [])
    monkeypatch.setattr(app, "schedule_projects", lambda projects: ({"Irene": {}}, []))
    monkeypatch.setattr(app, "active_workers", lambda today=None: ["Irene"])
    monkeypatch.setattr(app, "load_notes", lambda: [])
    monkeypatch.setattr(app, "load_extra_conflicts", lambda: [])
    monkeypatch.setattr(app, "load_dismissed", lambda: [])
    monkeypatch.setattr(app, "load_daily_hours", lambda: {})
    monkeypatch.setattr(app, "load_worker_notes", lambda: {})

    client = app.app.test_client()
    html = client.get("/calendar", headers=auth).get_data(as_text=True)
    idx = html.index("/toggle_freeze/")
    snippet = html[idx:idx+300]
    assert "location.reload" not in snippet
    assert "'Content-Type': 'application/json'" in snippet

    html2 = client.get("/complete", headers=auth).get_data(as_text=True)
    idx2 = html2.index("/toggle_freeze/")
    snippet2 = html2[idx2:idx2+300]
    assert "location.reload" not in snippet2
    assert "'Content-Type': 'application/json'" in snippet2


def test_refresh_after_move_and_hours(monkeypatch):
    auth = {"Authorization": "Basic " + base64.b64encode(b"admin:secreto").decode()}
    monkeypatch.setattr(app, "get_projects", lambda: [])
    monkeypatch.setattr(app, "schedule_projects", lambda projects: ({"Irene": {}}, []))
    monkeypatch.setattr(app, "active_workers", lambda today=None: ["Irene"])
    monkeypatch.setattr(app, "load_notes", lambda: [])
    monkeypatch.setattr(app, "load_extra_conflicts", lambda: [])
    monkeypatch.setattr(app, "load_dismissed", lambda: [])
    monkeypatch.setattr(app, "load_daily_hours", lambda: {})
    monkeypatch.setattr(app, "load_worker_notes", lambda: {})

    client = app.app.test_client()
    html = client.get("/calendar", headers=auth).get_data(as_text=True)
    assert "/calendar?json=1" in html
    idx = html.index("function afterMove")
    snippet = html[idx:idx+400]
    assert "refreshCalendar()" in snippet
    idx2 = html.index(".hours-form")
    snippet2 = html[idx2:idx2+600]
    assert "refreshCalendar" in snippet2
    assert "location.reload" not in snippet2


def test_refresh_updates_hours_and_removes(monkeypatch):
    auth = {"Authorization": "Basic " + base64.b64encode(b"admin:secreto").decode()}
    monkeypatch.setattr(app, "get_projects", lambda: [])
    monkeypatch.setattr(app, "schedule_projects", lambda projects: ({"Irene": {}}, []))
    monkeypatch.setattr(app, "active_workers", lambda today=None: ["Irene"])
    monkeypatch.setattr(app, "load_notes", lambda: [])
    monkeypatch.setattr(app, "load_extra_conflicts", lambda: [])
    monkeypatch.setattr(app, "load_dismissed", lambda: [])
    monkeypatch.setattr(app, "load_daily_hours", lambda: {})
    monkeypatch.setattr(app, "load_worker_notes", lambda: {})

    client = app.app.test_client()
    html = client.get("/calendar", headers=auth).get_data(as_text=True)
    idx = html.index("function moveTask")
    snippet = html[idx:idx+400]
    assert "task.dataset.hours" in snippet
    assert "task.querySelector('.task-hours')" in snippet
    idx2 = html.index("function refreshCalendar")
    snippet2 = html[idx2:idx2+800]
    assert "seen = new Set" in snippet2 or "seen = new Set();" in snippet2
    assert "el.remove();" in snippet2
