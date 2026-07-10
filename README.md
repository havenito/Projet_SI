# TP Systèmes d'Information avancés ou critiques

## Idée
Simuler une bactérie avec 4 états gérés en gRPC :
- stable vivant
- hypertrophie
- atrophie
- stable dans une impasse

L'application web affiche le volume, l'état courant et permet de déclencher les transitions autorisées. Le nombre de traversées de chaque état est exposé via Prometheus.

## Architecture
- 1 pod web/API
- 4 pods d'état gRPC
- stockage simple en SQLite pour conserver l'état des bactéries
- métriques Prometheus pour le comptage des passages d'état

## Lancement local

```bash
python -m pip install -r requirements.txt
python -m app.main state --state stable_vivant --grpc-port 50051 --metrics-port 9101
python -m app.main state --state hypertrophie --grpc-port 50052 --metrics-port 9102
python -m app.main state --state atrophie --grpc-port 50053 --metrics-port 9103
python -m app.main state --state stable_impasse --grpc-port 50054 --metrics-port 9104
python -m app.main api --host 0.0.0.0 --port 8000
```

## Test de performance

Outil choisi : **Apache JMeter**.

Le plan de test JMeter est disponible dans le dossier :

```text
tests/performance/
```

Il permet de simuler plusieurs utilisateurs envoyant des requêtes vers l'API afin de mesurer les performances, les temps de réponse et le débit de l'application.

## Déploiement

Les manifests Kubernetes sont disponibles dans le dossier `k8s`.