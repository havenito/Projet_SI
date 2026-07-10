# --- ÉTAPE DE CONSTRUCTION DE L'IMAGE DOCKER ---

# Utilisation d'une image de base Python officielle, légère (slim) et stable (Debian Bookworm)
FROM python:3.12.8-slim-bookworm

# Définition du répertoire de travail par défaut à l'intérieur du conteneur
WORKDIR /app

# Configuration des variables d'environnement pour optimiser l'exécution de Python en conteneur :
# 1. Empêche la génération des fichiers de cache compilés '.pyc' (allège le stockage)
# 2. Désactive la mise en tampon (buffering) des flux de sortie pour afficher instantanément les logs dans la console
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Copie d'abord uniquement le fichier des dépendances.
# Cela permet de mettre en cache cette couche (layer) et d'éviter de réinstaller les packages à chaque modification du code.
COPY requirements.txt .

# Installation des dépendances Python (FastAPI, Uvicorn, gRPC, Prometheus client, etc.)
# --no-cache-dir : Évite de stocker le cache des paquets téléchargés pour réduire la taille finale de l'image
# --prefer-binary : Télécharge les versions pré-compilées si disponibles pour accélérer l'installation
RUN pip install --no-cache-dir --prefer-binary -r requirements.txt

# Copie l'intégralité du code source du projet dans le dossier courant (/app) du conteneur
COPY . .

# Indication documentaire (métadonnée) spécifiant que le conteneur écoute par défaut sur le port 8000
EXPOSE 8000

# Commande d'exécution par défaut au lancement du conteneur : démarre l'API Web via Uvicorn.
# Note : Cette commande est automatiquement écrasée/remplacée par l'instruction 'command' dans les pods gRPC (Stable, Atrophie...) de ton manifeste Kubernetes.
CMD ["python", "-m", "app.main", "api", "--host", "0.0.0.0", "--port", "8000"]