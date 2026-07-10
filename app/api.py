from __future__ import annotations

from pathlib import Path
import os
from typing import Any

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

# Importation des constantes d'états, des modèles de données et des utilitaires métiers
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

# --- CONFIGURATION DE L'APPLICATION ---

# Définition du dossier racine du projet (deux niveaux au-dessus de ce fichier)
BASE_DIR = Path(__file__).resolve().parent.parent

# Configuration du moteur de templates Jinja2 pour le rendu des pages HTML
TEMPLATES = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Cartographie des états de la bactérie vers leurs serveurs gRPC respectifs via variables d'environnement
STATE_SERVICES = {
    STATE_STABLE: os.getenv("STATE_SERVICE_STABLE", "127.0.0.1:50051"),
    STATE_HYPERTROPHIE: os.getenv("STATE_SERVICE_HYPERTROPHIE", "127.0.0.1:50052"),
    STATE_ATROPHIE: os.getenv("STATE_SERVICE_ATROPHIE", "127.0.0.1:50053"),
    STATE_IMPASSE: os.getenv("STATE_SERVICE_IMPASSE", "127.0.0.1:50054"),
}

# Chemin vers la base de données SQLite (par défaut dans BASE_DIR/data/bacteria.db)
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", str(BASE_DIR / "data" / "bacteria.db")))

# Initialisation de l'API FastAPI et de la couche de stockage (Bdd)
app = FastAPI(title="TP Bactérie gRPC", version="1.0.0")
store = BacteriaStore(DATABASE_PATH)


# --- FONCTIONS FONCTIONNELLES ET HELPERS ---

def get_client(state: str) -> BacteriaStateClient:
    """Instancie un client gRPC spécifique pour l'état demandé."""
    return BacteriaStateClient(STATE_SERVICES[state])


def refresh_bacterium(snapshot: BacteriaSnapshot) -> BacteriaSnapshot:
    """
    Interroge le serveur gRPC de l'état actuel de la bactérie pour simuler son évolution.
    Si son état a changé, met à jour l'enregistrement dans la base de données.
    """
    client = get_client(snapshot.state)
    evolved = client.evolve(snapshot)  # Appel gRPC pour calculer l'évolution temporelle
    if evolved != snapshot:
        store.update(evolved)  # Sauvegarde si des modifications ont eu lieu
    return evolved


def current_snapshot(bacteria_id: str | None = None) -> BacteriaSnapshot:
    """
    Récupère une bactérie spécifique ou, par défaut, la première de la liste.
    Si la base est vide, elle lève une erreur ou initialise une bactérie par défaut.
    """
    bacteria_list = store.list_all()
    if not bacteria_list:
        return store.seed_default()  # Crée une bactérie par défaut si vide
    if bacteria_id is None:
        return bacteria_list[0]       # Retourne la première par défaut
    
    bacterium = store.get(bacteria_id)
    if bacterium is None:
        raise HTTPException(status_code=404, detail="Bactérie introuvable")
    return bacterium


# --- ÉVÉNEMENTS DU CYCLE DE VIE ---

@app.on_event("startup")
def on_startup() -> None:
    """Garantit la présence d'au moins une bactérie en base au démarrage de l'API."""
    store.seed_default()


# --- ENDPOINTS (ROUTES API & WEB) ---

@app.get("/", response_class=HTMLResponse)
def home(request: Request, bacteria_id: str | None = None) -> Any:
    """Affiche l'interface graphique (Dashboard) pour une bactérie donnée."""
    bacteria = current_snapshot(bacteria_id)
    bacteria = refresh_bacterium(bacteria)  # Met à jour la bactérie avant affichage
    
    # Récupère la description textuelle générée par le serveur gRPC lié à l'état
    description = get_client(bacteria.state).describe(bacteria)
    dashboard = build_dashboard()
    all_bacteria = store.list_all()
    
    # Rendu du template HTML avec injection des variables
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
    """API REST : Liste toutes les bactéries après avoir rafraîchi leur état."""
    return JSONResponse([
        _snapshot_to_dict(refresh_bacterium(bacterium)) for bacterium in store.list_all()
    ])


@app.get("/api/bacteria/{bacteria_id}")
def api_bacteria_detail(bacteria_id: str) -> JSONResponse:
    """API REST : Récupère les détails complets et les transitions autorisées d'une bactérie."""
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
    """API REST : Crée une nouvelle bactérie à l'état STABLE et notifie le service gRPC associé."""
    bacteria = store.create(
        name=name,
        state=STATE_STABLE,
        volume=1.0,
        last_action_at=now_ts() - 10,  # Force un décalage temporel initial
    )
    # Notifie le microservice de l'état STABLE qu'une nouvelle bactérie est entrée dans son scope
    get_client(STATE_STABLE).record_entry()
    return JSONResponse(_snapshot_to_dict(bacteria), status_code=201)


@app.post("/api/bacteria/{bacteria_id}/transition")
def transition_bacteria(bacteria_id: str, target_state: str = Form(...)) -> JSONResponse:
    """API REST : Demande au microservice gRPC de valider et d'appliquer un changement d'état."""
    bacterium = current_snapshot(bacteria_id)
    bacterium = refresh_bacterium(bacterium)
    
    client = get_client(bacterium.state)
    # Appel gRPC pour demander si la transition vers 'target_state' est biologiquement valide
    result = client.transition(TransitionRequest(current=bacterium, target_state=target_state))
    
    if not result.accepted:
        raise HTTPException(status_code=400, detail=result.message)

    # Mise à jour de la bactérie avec ses nouvelles propriétés validées
    store.update(result.bacteria)
    # Enregistrement de l'entrée dans le nouveau microservice d'état cible
    get_client(result.bacteria.state).record_entry()
    return JSONResponse(_snapshot_to_dict(result.bacteria))


@app.post("/api/bacteria/{bacteria_id}/tick")
def tick_bacteria(bacteria_id: str) -> JSONResponse:
    """API REST : Force manuellement une étape d'évolution temporelle (un 'tick') sur la bactérie."""
    bacterium = current_snapshot(bacteria_id)
    evolved = refresh_bacterium(bacterium)
    return JSONResponse(_snapshot_to_dict(evolved))


@app.get("/api/dashboard")
def api_dashboard() -> JSONResponse:
    """API REST : Renvoie les statistiques globales du tableau de bord."""
    return JSONResponse(build_dashboard())


# --- FONCTIONS DE FORMATAGE ET DE STATISTIQUES ---

def build_dashboard() -> dict[str, Any]:
    """Génère le dictionnaire de données du tableau de bord (compteur par état)."""
    return {"counts": store.counts_by_state()}


def _snapshot_to_dict(snapshot: BacteriaSnapshot) -> dict[str, Any]:
    """Sérialise un objet BacteriaSnapshot en dictionnaire Python pour l'export JSON."""
    return {
        "id": snapshot.id,
        "name": snapshot.name,
        "state": snapshot.state,
        "state_label": display_state(snapshot.state),  # Traduction/Formatage humain de l'état
        "volume": snapshot.volume,
        "last_action_at": snapshot.last_action_at,
        "created_at": snapshot.created_at,
        "updated_at": snapshot.updated_at,
        # Calcul dynamique des transitions possibles selon les règles définies dans les modèles
        "allowed_transitions": allowed_transitions_for(snapshot.state, snapshot.volume),
    }