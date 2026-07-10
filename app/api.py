from __future__ import annotations

from pathlib import Path
import os
from typing import Any

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from .models import (
    STATE_ATROPHIE,
    STATE_HYPERTROPHIE,
    STATE_IMPASSE,
    STATE_STABLE,
    BacteriaSnapshot,
    TransitionRequest,
    allowed_transitions_for,
    display_state,
    now_ts,
)
from .rpc import BacteriaStateClient
from .storage import BacteriaStore


BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES = Jinja2Templates(directory=str(BASE_DIR / "templates"))

STATE_SERVICES = {
    STATE_STABLE: os.getenv("STATE_SERVICE_STABLE", "127.0.0.1:50051"),
    STATE_HYPERTROPHIE: os.getenv("STATE_SERVICE_HYPERTROPHIE", "127.0.0.1:50052"),
    STATE_ATROPHIE: os.getenv("STATE_SERVICE_ATROPHIE", "127.0.0.1:50053"),
    STATE_IMPASSE: os.getenv("STATE_SERVICE_IMPASSE", "127.0.0.1:50054"),
}

DATABASE_PATH = Path(os.getenv("DATABASE_PATH", str(BASE_DIR / "data" / "bacteria.db")))

app = FastAPI(title="TP Bactérie gRPC", version="1.0.0")
store = BacteriaStore(DATABASE_PATH)


def get_client(state: str) -> BacteriaStateClient:
    return BacteriaStateClient(STATE_SERVICES[state])


def refresh_bacterium(snapshot: BacteriaSnapshot) -> BacteriaSnapshot:
    client = get_client(snapshot.state)
    evolved = client.evolve(snapshot)
    if evolved != snapshot:
        store.update(evolved)
    return evolved


def current_snapshot(bacteria_id: str | None = None) -> BacteriaSnapshot:
    bacteria_list = store.list_all()
    if not bacteria_list:
        return store.seed_default()
    if bacteria_id is None:
        return bacteria_list[0]
    bacterium = store.get(bacteria_id)
    if bacterium is None:
        raise HTTPException(status_code=404, detail="Bactérie introuvable")
    return bacterium


@app.on_event("startup")
def on_startup() -> None:
    store.seed_default()


@app.get("/", response_class=HTMLResponse)
def home(request: Request, bacteria_id: str | None = None) -> Any:
    bacteria = current_snapshot(bacteria_id)
    bacteria = refresh_bacterium(bacteria)
    description = get_client(bacteria.state).describe(bacteria)
    dashboard = build_dashboard()
    all_bacteria = store.list_all()
    return TEMPLATES.TemplateResponse(
        "index.html",
        {
            "request": request,
            "bacteria": bacteria,
            "description": description,
            "all_bacteria": all_bacteria,
            "dashboard": dashboard,
            "display_state": display_state,
        },
    )


@app.get("/api/bacteria")
def api_bacteria() -> JSONResponse:
    return JSONResponse([
        _snapshot_to_dict(refresh_bacterium(bacterium)) for bacterium in store.list_all()
    ])


@app.get("/api/bacteria/{bacteria_id}")
def api_bacteria_detail(bacteria_id: str) -> JSONResponse:
    bacterium = current_snapshot(bacteria_id)
    bacterium = refresh_bacterium(bacterium)
    description = get_client(bacterium.state).describe(bacterium)
    return JSONResponse(
        {
            "bacteria": _snapshot_to_dict(bacterium),
            "allowed_transitions": description.allowed_transitions,
            "traversals": description.traversals,
        }
    )


@app.post("/api/bacteria")
def create_bacteria(name: str = Form(default="Nouvelle bactérie")) -> JSONResponse:
    bacteria = store.create(
        name=name,
        state=STATE_STABLE,
        volume=1.0,
        last_action_at=now_ts() - 10,
    )
    get_client(STATE_STABLE).record_entry()
    return JSONResponse(_snapshot_to_dict(bacteria), status_code=201)


@app.post("/api/bacteria/{bacteria_id}/transition")
def transition_bacteria(bacteria_id: str, target_state: str = Form(...)) -> JSONResponse:
    bacterium = current_snapshot(bacteria_id)
    bacterium = refresh_bacterium(bacterium)
    client = get_client(bacterium.state)
    result = client.transition(TransitionRequest(current=bacterium, target_state=target_state))
    if not result.accepted:
        raise HTTPException(status_code=400, detail=result.message)

    store.update(result.bacteria)
    get_client(result.bacteria.state).record_entry()
    return JSONResponse(_snapshot_to_dict(result.bacteria))


@app.post("/api/bacteria/{bacteria_id}/tick")
def tick_bacteria(bacteria_id: str) -> JSONResponse:
    bacterium = current_snapshot(bacteria_id)
    evolved = refresh_bacterium(bacterium)
    return JSONResponse(_snapshot_to_dict(evolved))


@app.get("/api/dashboard")
def api_dashboard() -> JSONResponse:
    return JSONResponse(build_dashboard())


def build_dashboard() -> dict[str, Any]:
    return {"counts": store.counts_by_state()}


def _snapshot_to_dict(snapshot: BacteriaSnapshot) -> dict[str, Any]:
    return {
        "id": snapshot.id,
        "name": snapshot.name,
        "state": snapshot.state,
        "state_label": display_state(snapshot.state),
        "volume": snapshot.volume,
        "last_action_at": snapshot.last_action_at,
        "created_at": snapshot.created_at,
        "updated_at": snapshot.updated_at,
        "allowed_transitions": allowed_transitions_for(snapshot.state, snapshot.volume),
    }
