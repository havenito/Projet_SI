from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import time


STATE_STABLE = "stable_vivant"
STATE_HYPERTROPHIE = "hypertrophie"
STATE_ATROPHIE = "atrophie"
STATE_IMPASSE = "stable_impasse"

ALL_STATES = (
    STATE_STABLE,
    STATE_HYPERTROPHIE,
    STATE_ATROPHIE,
    STATE_IMPASSE,
)

STATE_LABELS = {
    STATE_STABLE: "Stable vivant, ouvert au changement",
    STATE_HYPERTROPHIE: "Hypertrophie",
    STATE_ATROPHIE: "Atrophie",
    STATE_IMPASSE: "Stable dans une impasse",
}


def now_ts() -> float:
    return time.time()


def ensure_state(state: str) -> str:
    if state not in ALL_STATES:
        raise ValueError(f"Etat inconnu: {state}")
    return state


def display_state(state: str) -> str:
    return STATE_LABELS.get(state, state)


def allowed_transitions_for(state: str, volume: float) -> list[str]:
    ensure_state(state)
    if state == STATE_STABLE:
        return [STATE_HYPERTROPHIE, STATE_ATROPHIE]
    if state == STATE_HYPERTROPHIE:
        return [STATE_STABLE]
    if state == STATE_ATROPHIE:
        options = [STATE_STABLE]
        if volume <= 0:
            options.append(STATE_IMPASSE)
        return options
    return []


def snapshot_to_payload(snapshot: "BacteriaSnapshot") -> dict[str, Any]:
    return asdict(snapshot)


def snapshot_from_payload(payload: dict[str, Any]) -> "BacteriaSnapshot":
    return BacteriaSnapshot(**payload)


@dataclass(slots=True)
class BacteriaSnapshot:
    id: str
    name: str
    state: str
    volume: float
    last_action_at: float
    created_at: float
    updated_at: float


@dataclass(slots=True)
class StateDescription:
    state: str
    label: str
    allowed_transitions: list[str]
    traversals: int
    note: str


@dataclass(slots=True)
class TransitionRequest:
    current: BacteriaSnapshot
    target_state: str


@dataclass(slots=True)
class TransitionResult:
    accepted: bool
    message: str
    bacteria: BacteriaSnapshot
    allowed_transitions: list[str]


@dataclass(slots=True)
class EntryResult:
    state: str
    traversals: int
