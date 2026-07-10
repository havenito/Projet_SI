from __future__ import annotations

import argparse

import uvicorn

# Importation de l'application FastAPI et des composants gRPC / modèles
from .api import app
from .models import STATE_ATROPHIE, STATE_HYPERTROPHIE, STATE_IMPASSE, STATE_STABLE
from .rpc import serve_state_service


def build_parser() -> argparse.ArgumentParser:
    """
    Configure le parseur d'arguments en ligne de commande (CLI).
    Permet de basculer entre le mode 'api' et le mode 'state' (microservice gRPC).
    """
    parser = argparse.ArgumentParser(description="TP bactérie gRPC")
    
    # Création de sous-commandes (ex: 'python main.py api' ou 'python main.py state')
    subparsers = parser.add_subparsers(dest="mode", required=True)

    # --- Configuration du sous-parseur pour l'API Web ---
    api_parser = subparsers.add_parser("api", help="Lance l'API web")
    api_parser.add_argument("--host", default="0.0.0.0", help="Adresse d'écoute de l'API")
    api_parser.add_argument("--port", type=int, default=8000, help="Port d'écoute de l'API")

    # --- Configuration du sous-parseur pour les microservices d'état ---
    state_parser = subparsers.add_parser("state", help="Lance un pod d'etat")
    # Restreint le choix de l'argument '--state' aux 4 états biologiques valides
    state_parser.add_argument(
        "--state", 
        choices=[STATE_STABLE, STATE_HYPERTROPHIE, STATE_ATROPHIE, STATE_IMPASSE], 
        required=True,
        help="L'état biologique que ce microservice doit gérer"
    )
    state_parser.add_argument("--grpc-port", type=int, required=True, help="Port d'écoute pour le serveur gRPC")
    state_parser.add_argument("--metrics-port", type=int, required=True, help="Port d'écoute pour l'exposition des métriques (Prometheus, etc.)")

    return parser


def main() -> None:
    """ Point d'entrée principal du script. """
    parser = build_parser()
    args = parser.parse_args()  # Analyse les arguments passés dans le terminal

    # Si l'utilisateur a tapé 'api', on lance le serveur Web Uvicorn avec FastAPI
    if args.mode == "api":
        uvicorn.run(app, host=args.host, port=args.port)
        return

    # Sinon (si l'utilisateur a tapé 'state'), on lance le serveur gRPC pour l'état spécifié
    serve_state_service(args.state, args.grpc_port, args.metrics_port)


if __name__ == "__main__":
    main()