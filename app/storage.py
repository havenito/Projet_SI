from __future__ import annotations

from pathlib import Path
import sqlite3
import threading

# Importation du modèle de base et de la constante de l'état initial
from .models import STATE_STABLE, BacteriaSnapshot, now_ts


class BacteriaStore:
    """
    Couche d'accès aux données (DAO).
    Gère la persistance des bactéries dans une base de données SQLite.
    Sécurisée pour les accès concurrents grâce à un verrou de thread (Lock).
    """
    
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self._lock = threading.Lock()  # Assure qu'un seul thread n'écrive en base à la fois
        
        # Crée automatiquement le dossier parent du fichier de base de données s'il n'existe pas
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        """Crée et configure une connexion à la base de données SQLite."""
        connection = sqlite3.connect(self.database_path)
        # Permet d'accéder aux colonnes par leur nom comme un dictionnaire (ex: row["name"])
        connection.row_factory = sqlite3.Row
        # Active le mode WAL pour gérer efficacement les lectures/écritures simultanées
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def _initialize(self) -> None:
        """Crée la table 'bacteria' lors du démarrage si elle n'existe pas encore."""
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS bacteria (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    state TEXT NOT NULL,
                    volume REAL NOT NULL,
                    last_action_at REAL NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            connection.commit()

    def seed_default(self) -> BacteriaSnapshot:
        """Insère une bactérie initiale par défaut si la base de données est complètement vide."""
        existing = self.list_all()
        if existing:
            return existing[0]  # Si des données existent, renvoie simplement la première

        # Génération de la première bactérie de test
        return self.create(
            name="Bactérie 1",
            state=STATE_STABLE,
            volume=1.0,
            last_action_at=now_ts() - 10,
        )

    def list_all(self) -> list[BacteriaSnapshot]:
        """Récupère l'intégralité des bactéries triées par ordre chronologique de création."""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, name, state, volume, last_action_at, created_at, updated_at FROM bacteria ORDER BY created_at"
            ).fetchall()
        # Convertit chaque ligne SQLite brute en un objet typé BacteriaSnapshot
        return [self._row_to_snapshot(row) for row in rows]

    def get(self, bacteria_id: str) -> BacteriaSnapshot | None:
        """Recherche et renvoie une bactérie par son identifiant unique unique (id)."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, name, state, volume, last_action_at, created_at, updated_at FROM bacteria WHERE id = ?",
                (bacteria_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_snapshot(row)

    def create(
        self,
        *,
        name: str,
        state: str,
        volume: float,
        last_action_at: float,
    ) -> BacteriaSnapshot:
        """
        Génère, stocke en base et retourne une toute nouvelle instance de bactérie.
        L'écriture est synchronisée et sécurisée par thread.
        """
        current_time = now_ts()
        # Génération d'un ID unique basé sur le timestamp actuel en millisecondes (ex: bact-1710000000123)
        bacteria = BacteriaSnapshot(
            id=f"bact-{int(current_time * 1000)}",
            name=name,
            state=state,
            volume=round(volume, 4),
            last_action_at=last_action_at,
            created_at=current_time,
            updated_at=current_time,
        )
        
        # Utilisation du Lock pour interdire l'écriture simultanée par un autre thread d'API
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO bacteria (id, name, state, volume, last_action_at, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    bacteria.id,
                    bacteria.name,
                    bacteria.state,
                    bacteria.volume,
                    bacteria.last_action_at,
                    bacteria.created_at,
                    bacteria.updated_at,
                ),
            )
            connection.commit()
        return bacteria

    def update(self, bacteria: BacteriaSnapshot) -> None:
        """
        Met à jour l'ensemble des informations d'une bactérie existante.
        Actualise automatiquement la valeur 'updated_at' avec le timestamp courant.
        """
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE bacteria
                SET name = ?, state = ?, volume = ?, last_action_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    bacteria.name,
                    bacteria.state,
                    round(bacteria.volume, 4),
                    bacteria.last_action_at,
                    now_ts(),  # Nouvelle date de mise à jour
                    bacteria.id,
                ),
            )
            connection.commit()

    def counts_by_state(self) -> dict[str, int]:
        """
        Agrège et calcule le nombre total de bactéries actuellement présentes dans chaque état.
        Retourne un dictionnaire prêt à être consommé par le Dashboard.
        """
        # Initialisation par défaut de tous les compteurs d'état à 0
        counts = {
            "stable_vivant": 0,
            "hypertrophie": 0,
            "atrophie": 0,
            "stable_impasse": 0,
        }
        with self._connect() as connection:
            # Exécution d'une requête SQL d'agrégation (GROUP BY)
            rows = connection.execute(
                "SELECT state, COUNT(*) AS total FROM bacteria GROUP BY state"
            ).fetchall()
        
        # Injection des résultats de la requête dans le dictionnaire
        for row in rows:
            counts[row["state"]] = row["total"]
        return counts

    def _row_to_snapshot(self, row: sqlite3.Row) -> BacteriaSnapshot:
        """Méthode utilitaire privée convertissant une ligne SQLite en objet BacteriaSnapshot."""
        return BacteriaSnapshot(
            id=row["id"],
            name=row["name"],
            state=row["state"],
            volume=row["volume"],
            last_action_at=row["last_action_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )