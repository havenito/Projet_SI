from __future__ import annotations

# L'utilitaire 'replace' de dataclasses permet de cloner un objet 
# en modifiant uniquement certains attributs (pratique car les dataclasses sont lues/écrites souvent)
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
    """
    Moteur logique exécuté au sein de chaque microservice d'état.
    Gère l'évolution temporelle (volume) et la validation des transitions pour un état donné.
    """
    
    def __init__(self, state_name: str) -> None:
        # Stocke le nom de l'état géré par le pod gRPC actuel
        self.state_name = state_name

    def describe(self, snapshot: BacteriaSnapshot, traversals: int) -> StateDescription:
        """Génère un rapport complet de l'état de la bactérie avec sa note explicative."""
        return StateDescription(
            state=self.state_name,
            label=display_state(self.state_name),
            allowed_transitions=allowed_transitions_for(snapshot.state, snapshot.volume),
            traversals=traversals,
            note=self._note(),  # Récupère le message personnalisé lié à l'état
        )

    def evolve(self, snapshot: BacteriaSnapshot) -> BacteriaSnapshot:
        """
        Simule le vieillissement / l'évolution biologique de la bactérie.
        Modifie le volume de la bactérie de manière passive par tranches de 10 secondes.
        """
        current_time = now_ts()
        # Par défaut, on met systématiquement à jour la date de rafraîchissement
        updated = replace(snapshot, updated_at=current_time)

        # --- Logique de l'état HYPERTROPHIE ---
        if self.state_name == STATE_HYPERTROPHIE:
            # Si 10 secondes ou plus se sont écoulées depuis la dernière mise à jour de volume
            if current_time - snapshot.last_action_at >= 10:
                updated = replace(
                    updated,
                    volume=round(snapshot.volume * 1.10, 4),  # Gain de +10% de volume
                    last_action_at=current_time,              # Réinitialise le timer d'action
                )
                
        # --- Logique de l'état ATROPHIE ---
        elif self.state_name == STATE_ATROPHIE:
            # Si 10 secondes ou plus se sont écoulées depuis la dernière mise à jour de volume
            if current_time - snapshot.last_action_at >= 10:
                updated = replace(
                    updated,
                    volume=round(snapshot.volume * 0.95, 4),  # Perte de -5% de volume
                    last_action_at=current_time,              # Réinitialise le timer d'action
                )

        return updated

    def transition(self, request: TransitionRequest) -> TransitionResult:
        """
        Vérifie et applique le passage de la bactérie vers un nouvel état cible.
        """
        current = request.current
        target_state = request.target_state
        # Calcule les transitions autorisées pour la bactérie en fonction de ses critères actuels
        allowed = allowed_transitions_for(current.state, current.volume)

        # Refus si l'état demandé ne fait pas partie des règles de la machine à états
        if target_state not in allowed:
            return TransitionResult(
                accepted=False,
                message=f"Transition interdite de {current.state} vers {target_state}",
                bacteria=current,
                allowed_transitions=allowed,
            )

        # Si accepté, on prépare le snapshot modifié de la bactérie
        current_time = now_ts()
        next_snapshot = replace(
            current,
            state=target_state,
            updated_at=current_time,
            # Si on passe sur un état actif (Hypertrophie/Atrophie), on synchronise la date d'action
            # pour démarrer le décompte des 10 secondes proprement. Sinon, on garde l'historique.
            last_action_at=current_time if target_state in {STATE_HYPERTROPHIE, STATE_ATROPHIE} else current.last_action_at,
        )

        return TransitionResult(
            accepted=True,
            message=f"Transition validée vers {target_state}",
            bacteria=next_snapshot,
            # Renvoie la liste des nouvelles transitions futures possibles depuis l'état cible
            allowed_transitions=allowed_transitions_for(target_state, next_snapshot.volume),
        )

    def record_entry(self, traversals: int) -> EntryResult:
        """Incrémente manuellement et renvoie le compteur de passages (utilisé en secours du monitoring)."""
        return EntryResult(state=self.state_name, traversals=traversals + 1)

    def _note(self) -> str:
        """Documentation interne affichée sur le Dashboard pour expliquer les règles de l'état courant."""
        if self.state_name == STATE_STABLE:
            return "Etat d'accueil: accepte hypertrophie ou atrophie."
        if self.state_name == STATE_HYPERTROPHIE:
            return "Augmente de 10% toutes les 10 secondes."
        if self.state_name == STATE_ATROPHIE:
            return "Perd 5% toutes les 10 secondes."
        if self.state_name == STATE_IMPASSE:
            return "Aucune transition disponible."
        return ""