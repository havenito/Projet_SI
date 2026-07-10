from __future__ import annotations

# Importation des outils Prometheus pour le monitoring
from prometheus_client import Counter, start_http_server

# Définition d'une métrique de type Compteur (Counter).
# Ce compteur suit le nombre total de transitions/traversées pour chaque état.
# Le label ["state"] permet de filtrer dynamiquement les résultats par état (ex: stable, hypertrophie).
STATE_TRAVERSALS = Counter(
    "bacteria_state_traversals_total",
    "Nombre de fois qu'un etat a ete traverse",
    ["state"],
)


def start_metrics_server(port: int) -> None:
    """
    Démarre un serveur HTTP indépendant sur le port spécifié.
    Ce serveur expose le point d'accès '/metrics' que Prometheus viendra scraper régulièrement.
    """
    start_http_server(port)


def increment_state(state: str) -> None:
    """
    Incrémente de +1 le compteur pour un état spécifique.
    Exemple : increment_state("STABLE") va cibler la métrique avec le label state="STABLE".
    """
    STATE_TRAVERSALS.labels(state=state).inc()