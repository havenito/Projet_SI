from __future__ import annotations

from pathlib import Path
import sqlite3
import threading

from .models import STATE_STABLE, BacteriaSnapshot, now_ts


class BacteriaStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self._lock = threading.Lock()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def _initialize(self) -> None:
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
        existing = self.list_all()
        if existing:
            return existing[0]

        return self.create(
            name="Bactérie 1",
            state=STATE_STABLE,
            volume=1.0,
            last_action_at=now_ts() - 10,
        )

    def list_all(self) -> list[BacteriaSnapshot]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, name, state, volume, last_action_at, created_at, updated_at FROM bacteria ORDER BY created_at"
            ).fetchall()
        return [self._row_to_snapshot(row) for row in rows]

    def get(self, bacteria_id: str) -> BacteriaSnapshot | None:
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
        current_time = now_ts()
        bacteria = BacteriaSnapshot(
            id=f"bact-{int(current_time * 1000)}",
            name=name,
            state=state,
            volume=round(volume, 4),
            last_action_at=last_action_at,
            created_at=current_time,
            updated_at=current_time,
        )
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
                    now_ts(),
                    bacteria.id,
                ),
            )
            connection.commit()

    def counts_by_state(self) -> dict[str, int]:
        counts = {
            "stable_vivant": 0,
            "hypertrophie": 0,
            "atrophie": 0,
            "stable_impasse": 0,
        }
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT state, COUNT(*) AS total FROM bacteria GROUP BY state"
            ).fetchall()
        for row in rows:
            counts[row["state"]] = row["total"]
        return counts

    def _row_to_snapshot(self, row: sqlite3.Row) -> BacteriaSnapshot:
        return BacteriaSnapshot(
            id=row["id"],
            name=row["name"],
            state=row["state"],
            volume=row["volume"],
            last_action_at=row["last_action_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
