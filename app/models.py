from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import time

# --- CONSTANTES DES ÉTATS BIOLOGIQUES ---
STATE_STABLE = "stable_vivant"
STATE_HYPERTROPHIE = "hypertrophie"
STATE_ATROPHIE = "atrophie"
STATE_IMPASSE = "stable_impasse"

# Liste globale de validation de tous les états possibles
ALL_STATES = (
    STATE_STABLE,
    STATE_HYPERTROPHIE,
    STATE_ATROPHIE,
    STATE_IMPASSE,
)

# Libellés (labels) pour l'affichage dans l'interface utilisateur graphique (UI)
STATE_LABELS = {
    STATE_STABLE: "Stable vivant, ouvert au changement",
    STATE_HYPERTROPHIE: "Hypertrophie",
    STATE_ATROPHIE: "Atrophie",
    STATE_IMPASSE: "Stable dans une impasse",
}


# --- UTILS & VALIDATIONS ---

def now_ts() -> float:
    """Retourne le timestamp actuel (Epoch time) en secondes sous forme de float."""
    return time.time()


def ensure_state(state: str) -> str:
    """Valide si l'état fourni existe. Lève une erreur s'il est inconnu."""
    if state not in ALL_STATES:
        raise ValueError(f"Etat inconnu: {state}")
    return state


def display_state(state: str) -> str:
    """Retourne le libellé lisible associé à un état, ou l'état brut si inconnu."""
    return STATE_LABELS.get(state, state)


def allowed_transitions_for(state: str, volume: float) -> list[str]:
    """
    Machine à états (State Machine) de la bactérie.
    Définit les transitions autorisées selon l'état actuel et le volume de la bactérie.
    """
    ensure_state(state)
    
    # Depuis l'état STABLE, on peut grossir (HYPERTROPHIE) ou rétrécir (ATROPHIE)
    if state == STATE_STABLE:
        return [STATE_HYPERTROPHIE, STATE_ATROPHIE]
        
    # Depuis l'état HYPERTROPHIE, on ne peut que revenir à l'état STABLE
    if state == STATE_HYPERTROPHIE:
        return [STATE_STABLE]
        
    # Depuis l'état ATROPHIE, on peut revenir à l'état STABLE, 
    # et si le volume tombe à 0 ou moins, la bactérie entre dans une IMPASSE
    if state == STATE_ATROPHIE:
        options = [STATE_STABLE]
        if volume <= 0:
            options.append(STATE_IMPASSE)
        return options
        
    # L'état IMPASSE est terminal : aucune transition sortante possible
    return []


# --- SÉRIALISATION / DÉSÉRIALISATION ---

def snapshot_to_payload(snapshot: "BacteriaSnapshot") -> dict[str, Any]:
    """Convertit une Dataclass BacteriaSnapshot en dictionnaire classique Python."""
    return asdict(snapshot)


def snapshot_from_payload(payload: dict[str, Any]) -> "BacteriaSnapshot":
    """Instancie un objet BacteriaSnapshot à partir d'un dictionnaire de données."""
    return BacteriaSnapshot(**payload)


# --- STRUCTURES DE DONNÉES (DATACLASSES) ---
# Note: slots=True optimise la mémoire et la vitesse d'accès aux attributs

@dataclass(slots=True)
class BacteriaSnapshot:
    """Représentation figée (snapshot) de l'état d'une bactérie à un instant T."""
    id: str
    name: str
    state: str
    volume: float
    last_action_at: float  # Timestamp de la dernière action subie
    created_at: float      # Timestamp de création
    updated_at: float      # Timestamp de dernière mise à jour


@dataclass(slots=True)
class StateDescription:
    """Description complète d'un état généré par le microservice gRPC associé."""
    state: str
    label: str
    allowed_transitions: list[str]
    traversals: int        # Nombre total de passages dans cet état (métrique)
    note: str              # Information textuelle libre ou diagnostic du serveur


@dataclass(slots=True)
class TransitionRequest:
    """Payload envoyé pour demander un changement d'état."""
    current: BacteriaSnapshot
    target_state: str


@dataclass(slots=True)
class TransitionResult:
    """Réponse d'un service gRPC suite à une tentative de transition."""
    accepted: bool                  # True si le changement d'état respecte les règles
    message: str                   # Raison du refus ou détails du succès
    bacteria: BacteriaSnapshot     # La bactérie mise à jour après transition
    allowed_transitions: list[str] # Les nouvelles transitions désormais possibles


@dataclass(slots=True)
class EntryResult:
    """Résultat du signalement de l'entrée d'une bactérie dans un service d'état."""
    state: str
    traversals: int                # Nouveau compteur de traversées du service après incrément