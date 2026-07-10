from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from dataclasses import asdict
from typing import Any

import grpc

# Importation des métriques Prometheus et des modèles de données
from .metrics import increment_state, start_metrics_server
from .models import (
    BacteriaSnapshot,
    EntryResult,
    StateDescription,
    TransitionRequest,
    TransitionResult,
    snapshot_from_payload,
    snapshot_to_payload,
)
from .state_logic import StateMachine


# --- SERALISATEURS / DESERIALISATEURS PERSO (ALTERNATIVE A PROTOBUF) ---

def _dump(payload: Any) -> bytes:
    """Sérialise un objet Python en chaîne JSON encodée en bytes UTF-8 (sans espaces superflus)."""
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _load(data: bytes) -> dict[str, Any]:
    """Décode des bytes UTF-8 pour reconstruire un dictionnaire Python depuis du JSON."""
    return json.loads(data.decode("utf-8"))


# --- FONCTIONS DE CONVERSION (MAPPING DATACLASS <-> DICTIONNAIRE) ---

def _snapshot_to_dict(snapshot: BacteriaSnapshot) -> dict[str, Any]:
    return snapshot_to_payload(snapshot)


def _snapshot_from_dict(payload: dict[str, Any]) -> BacteriaSnapshot:
    return snapshot_from_payload(payload)


def _transition_request_from_dict(payload: dict[str, Any]) -> TransitionRequest:
    return TransitionRequest(
        current=_snapshot_from_dict(payload["current"]),
        target_state=payload["target_state"],
    )


def _describe_to_dict(describe: StateDescription) -> dict[str, Any]:
    return asdict(describe)


def _transition_result_to_dict(result: TransitionResult) -> dict[str, Any]:
    return {
        "accepted": result.accepted,
        "message": result.message,
        "bacteria": _snapshot_to_dict(result.bacteria),
        "allowed_transitions": result.allowed_transitions,
    }


def _entry_result_to_dict(result: EntryResult) -> dict[str, Any]:
    return asdict(result)


# --- CÔTÉ SERVEUR : LE SERVICER gRPC ---

class BacteriaStateServicer:
    """Gère la réception et le traitement des requêtes RPC reçues par le microservice d'état."""
    
    def __init__(self, state_name: str) -> None:
        self.state_name = state_name
        self.logic = StateMachine(state_name)  # Charge la logique métier propre à cet état
        self.traversals = 0                    # Compteur local de passages dans cet état

    def Describe(self, request: bytes, context: grpc.ServicerContext) -> bytes:
        """RPC : Renvoie une description textuelle et biologique de la bactérie."""
        snapshot = _snapshot_from_dict(_load(request))
        description = self.logic.describe(snapshot, self.traversals)
        return _dump(_describe_to_dict(description))

    def Evolve(self, request: bytes, context: grpc.ServicerContext) -> bytes:
        """RPC : Calcule l'évolution temporelle de la bactérie."""
        snapshot = _snapshot_from_dict(_load(request))
        evolved = self.logic.evolve(snapshot)
        return _dump(_snapshot_to_dict(evolved))

    def Transition(self, request: bytes, context: grpc.ServicerContext) -> bytes:
        """RPC : Valide si une bactérie peut légitimement changer d'état."""
        payload = _load(request)
        transition_request = _transition_request_from_dict(payload)
        result = self.logic.transition(transition_request)
        return _dump(_transition_result_to_dict(result))

    def RecordEntry(self, request: bytes, context: grpc.ServicerContext) -> bytes:
        """RPC : Enregistre le passage d'une bactérie dans cet état et incrémente Prometheus."""
        self.traversals += 1
        increment_state(self.state_name)  # Met à jour la métrique globale Prometheus
        return _dump(_entry_result_to_dict(EntryResult(state=self.state_name, traversals=self.traversals)))


def add_bacteria_state_servicer(server: grpc.Server, servicer: BacteriaStateServicer) -> None:
    """
    Enregistre manuellement le Servicer sur le serveur gRPC.
    Puisqu'on n'utilise pas de fichier .proto généré, on crée un handler générique 'unary_unary'.
    """
    handler = grpc.method_handlers_generic_handler(
        "bacteria.BacteriaState",
        {
            "Describe": grpc.unary_unary_rpc_method_handler(
                servicer.Describe,
                request_deserializer=lambda data: data,  # On laisse passer les bytes bruts
                response_serializer=lambda data: data,
            ),
            "Evolve": grpc.unary_unary_rpc_method_handler(
                servicer.Evolve,
                request_deserializer=lambda data: data,
                response_serializer=lambda data: data,
            ),
            "Transition": grpc.unary_unary_rpc_method_handler(
                servicer.Transition,
                request_deserializer=lambda data: data,
                response_serializer=lambda data: data,
            ),
            "RecordEntry": grpc.unary_unary_rpc_method_handler(
                servicer.RecordEntry,
                request_deserializer=lambda data: data,
                response_serializer=lambda data: data,
            ),
        },
    )
    server.add_generic_rpc_handlers((handler,))


# --- CÔTÉ CLIENT : LE CLIENT gRPC ---

class BacteriaStateClient:
    """Client RPC utilisé par l'API FastAPI pour communiquer avec les différents microservices d'états."""
    
    def __init__(self, target: str) -> None:
        # Ouvre un canal de communication non sécurisé (HTTP/2 brut) vers le microservice ciblé
        self.channel = grpc.insecure_channel(target)

    def _call(self, method_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Méthode interne générique pour effectuer l'appel RPC réseau."""
        method = self.channel.unary_unary(
            f"/bacteria.BacteriaState/{method_name}",
            request_serializer=_dump,       # Sérialise automatiquement le dictionnaire en JSON bytes
            response_deserializer=_load,     # Désérialise automatiquement les bytes reçus en dict
        )
        return method(payload)

    def describe(self, snapshot: BacteriaSnapshot) -> StateDescription:
        """Demande la description de l'état au serveur gRPC distant."""
        payload = self._call("Describe", _snapshot_to_dict(snapshot))
        return StateDescription(**payload)

    def evolve(self, snapshot: BacteriaSnapshot) -> BacteriaSnapshot:
        """Demande l'évolution de la bactérie au serveur gRPC distant."""
        payload = self._call("Evolve", _snapshot_to_dict(snapshot))
        return _snapshot_from_dict(payload)

    def transition(self, request: TransitionRequest) -> TransitionResult:
        """Envoie une demande de transition d'état au serveur gRPC distant."""
        payload = self._call(
            "Transition",
            {
                "current": _snapshot_to_dict(request.current),
                "target_state": request.target_state,
            },
        )
        return TransitionResult(
            accepted=payload["accepted"],
            message=payload["message"],
            bacteria=_snapshot_from_dict(payload["bacteria"]),
            allowed_transitions=list(payload["allowed_transitions"]),
        )

    def record_entry(self) -> EntryResult:
        """Notifie le serveur gRPC qu'une bactérie vient d'adopter son état."""
        payload = self._call("RecordEntry", {})
        return EntryResult(**payload)


# --- INITIALISATION ET LANCEMENT DU POD ---

def serve_state_service(state_name: str, grpc_port: int, metrics_port: int) -> None:
    """Démarre le serveur gRPC d'état biologique ainsi que son serveur de métriques associé."""
    # Création du serveur gRPC avec un pool de 8 threads pour gérer les requêtes en parallèle
    server = grpc.server(ThreadPoolExecutor(max_workers=8))
    
    # Enregistrement du gestionnaire de requêtes
    add_bacteria_state_servicer(server, BacteriaStateServicer(state_name))
    
    # Écoute sur toutes les interfaces réseau (IPv6/IPv4) sur le port spécifié
    server.add_insecure_port(f"[::]:{grpc_port}")
    server.start()
    
    # Lancement du serveur Prometheus HTTP pour exposer les métriques
    start_metrics_server(metrics_port)
    
    # Maintient le script en vie tant que le serveur gRPC tourne
    server.wait_for_termination()