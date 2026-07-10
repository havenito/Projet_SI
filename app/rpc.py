from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from dataclasses import asdict
from typing import Any

import grpc

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


def _dump(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _load(data: bytes) -> dict[str, Any]:
    return json.loads(data.decode("utf-8"))


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


class BacteriaStateServicer:
    def __init__(self, state_name: str) -> None:
        self.state_name = state_name
        self.logic = StateMachine(state_name)
        self.traversals = 0

    def Describe(self, request: bytes, context: grpc.ServicerContext) -> bytes:
        snapshot = _snapshot_from_dict(_load(request))
        description = self.logic.describe(snapshot, self.traversals)
        return _dump(_describe_to_dict(description))

    def Evolve(self, request: bytes, context: grpc.ServicerContext) -> bytes:
        snapshot = _snapshot_from_dict(_load(request))
        evolved = self.logic.evolve(snapshot)
        return _dump(_snapshot_to_dict(evolved))

    def Transition(self, request: bytes, context: grpc.ServicerContext) -> bytes:
        payload = _load(request)
        transition_request = _transition_request_from_dict(payload)
        result = self.logic.transition(transition_request)
        return _dump(_transition_result_to_dict(result))

    def RecordEntry(self, request: bytes, context: grpc.ServicerContext) -> bytes:
        self.traversals += 1
        increment_state(self.state_name)
        return _dump(_entry_result_to_dict(EntryResult(state=self.state_name, traversals=self.traversals)))


def add_bacteria_state_servicer(server: grpc.Server, servicer: BacteriaStateServicer) -> None:
    handler = grpc.method_handlers_generic_handler(
        "bacteria.BacteriaState",
        {
            "Describe": grpc.unary_unary_rpc_method_handler(
                servicer.Describe,
                request_deserializer=lambda data: data,
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


class BacteriaStateClient:
    def __init__(self, target: str) -> None:
        self.channel = grpc.insecure_channel(target)

    def _call(self, method_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        method = self.channel.unary_unary(
            f"/bacteria.BacteriaState/{method_name}",
            request_serializer=_dump,
            response_deserializer=_load,
        )
        return method(payload)

    def describe(self, snapshot: BacteriaSnapshot) -> StateDescription:
        payload = self._call("Describe", _snapshot_to_dict(snapshot))
        return StateDescription(**payload)

    def evolve(self, snapshot: BacteriaSnapshot) -> BacteriaSnapshot:
        payload = self._call("Evolve", _snapshot_to_dict(snapshot))
        return _snapshot_from_dict(payload)

    def transition(self, request: TransitionRequest) -> TransitionResult:
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
        payload = self._call("RecordEntry", {})
        return EntryResult(**payload)


def serve_state_service(state_name: str, grpc_port: int, metrics_port: int) -> None:
    server = grpc.server(ThreadPoolExecutor(max_workers=8))
    add_bacteria_state_servicer(server, BacteriaStateServicer(state_name))
    server.add_insecure_port(f"[::]:{grpc_port}")
    server.start()
    start_metrics_server(metrics_port)
    server.wait_for_termination()
