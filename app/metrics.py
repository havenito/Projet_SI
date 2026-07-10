from __future__ import annotations

from prometheus_client import Counter, start_http_server


STATE_TRAVERSALS = Counter(
    "bacteria_state_traversals_total",
    "Nombre de fois qu'un etat a ete traverse",
    ["state"],
)


def start_metrics_server(port: int) -> None:
    start_http_server(port)


def increment_state(state: str) -> None:
    STATE_TRAVERSALS.labels(state=state).inc()
