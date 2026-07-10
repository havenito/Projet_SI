from __future__ import annotations

from dataclasses import replace

from .models import (
    STATE_ATROPHIE,
    STATE_HYPERTROPHIE,
    STATE_IMPASSE,
    STATE_STABLE,
    BacteriaSnapshot,
    EntryResult,
    StateDescription,
    TransitionRequest,
    TransitionResult,
    allowed_transitions_for,
    display_state,
    now_ts,
)


class StateMachine:
    def __init__(self, state_name: str) -> None:
        self.state_name = state_name

    def describe(self, snapshot: BacteriaSnapshot, traversals: int) -> StateDescription:
        return StateDescription(
            state=self.state_name,
            label=display_state(self.state_name),
            allowed_transitions=allowed_transitions_for(snapshot.state, snapshot.volume),
            traversals=traversals,
            note=self._note(),
        )

    def evolve(self, snapshot: BacteriaSnapshot) -> BacteriaSnapshot:
        current_time = now_ts()
        updated = replace(snapshot, updated_at=current_time)

        if self.state_name == STATE_HYPERTROPHIE:
            if current_time - snapshot.last_action_at >= 10:
                updated = replace(
                    updated,
                    volume=round(snapshot.volume * 1.10, 4),
                    last_action_at=current_time,
                )
        elif self.state_name == STATE_ATROPHIE:
            if current_time - snapshot.last_action_at >= 10:
                updated = replace(
                    updated,
                    volume=round(snapshot.volume * 0.95, 4),
                    last_action_at=current_time,
                )

        return updated

    def transition(self, request: TransitionRequest) -> TransitionResult:
        current = request.current
        target_state = request.target_state
        allowed = allowed_transitions_for(current.state, current.volume)

        if target_state not in allowed:
            return TransitionResult(
                accepted=False,
                message=f"Transition interdite de {current.state} vers {target_state}",
                bacteria=current,
                allowed_transitions=allowed,
            )

        current_time = now_ts()
        next_snapshot = replace(
            current,
            state=target_state,
            updated_at=current_time,
            last_action_at=current_time if target_state in {STATE_HYPERTROPHIE, STATE_ATROPHIE} else current.last_action_at,
        )

        return TransitionResult(
            accepted=True,
            message=f"Transition validée vers {target_state}",
            bacteria=next_snapshot,
            allowed_transitions=allowed_transitions_for(target_state, next_snapshot.volume),
        )

    def record_entry(self, traversals: int) -> EntryResult:
        return EntryResult(state=self.state_name, traversals=traversals + 1)

    def _note(self) -> str:
        if self.state_name == STATE_STABLE:
            return "Etat d'accueil: accepte hypertrophie ou atrophie."
        if self.state_name == STATE_HYPERTROPHIE:
            return "Augmente de 10% toutes les 10 secondes."
        if self.state_name == STATE_ATROPHIE:
            return "Perd 5% toutes les 10 secondes."
        if self.state_name == STATE_IMPASSE:
            return "Aucune transition disponible."
        return ""
