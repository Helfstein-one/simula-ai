"""adapters/outbound/sqlite_state_adapter.py - SQLite & JSONL state persistence adapter."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from application.ports.state_repository_port import StateRepositoryPort
from domain.state import SimulaState


class SqliteStateAdapter(StateRepositoryPort):
    """Persists simulation state checkpoints and episodic traces to SQLite database and JSONL."""

    def __init__(self, db_path: Optional[str | Path] = None) -> None:
        self.db_path = Path(db_path or "output/simula_history.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS simula_sessions (
                    session_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    final_status TEXT,
                    total_iterations INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS simula_checkpoints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    iteration INTEGER NOT NULL,
                    status TEXT,
                    message TEXT,
                    state_json TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES simula_sessions(session_id)
                );

                CREATE INDEX IF NOT EXISTS idx_checkpoints_session 
                ON simula_checkpoints(session_id, iteration);
                """
            )

    def save_checkpoint(
        self,
        session_id: str,
        iteration: int,
        state: SimulaState,
        status: str = "",
        message: str = "",
    ) -> None:
        now = datetime.now(UTC).isoformat()
        st_status = status or state.get("status", "")
        # Serialize state safely
        clean_state = {
            "iterations": state.get("iterations", iteration),
            "max_iterations": state.get("max_iterations", 5),
            "status": st_status,
            "working_memory": state.get("working_memory", {}),
            "episodic_memory": state.get("episodic_memory", []),
            "error_message": state.get("error_message"),
        }
        state_str = json.dumps(clean_state, default=str)

        with self._get_connection() as conn:
            # Upsert session
            conn.execute(
                """
                INSERT INTO simula_sessions (session_id, created_at, updated_at, final_status, total_iterations)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    updated_at = excluded.updated_at,
                    final_status = excluded.final_status,
                    total_iterations = MAX(total_iterations, excluded.total_iterations)
                """,
                (session_id, now, now, st_status, iteration),
            )

            # Insert checkpoint
            conn.execute(
                """
                INSERT INTO simula_checkpoints (session_id, iteration, status, message, state_json, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (session_id, iteration, st_status, message, state_str, now),
            )

    def get_session_history(self, session_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT id, session_id, iteration, status, message, state_json, timestamp
                FROM simula_checkpoints
                WHERE session_id = ?
                ORDER BY id ASC
                """,
                (session_id,),
            )
            rows = cursor.fetchall()

        history: List[Dict[str, Any]] = []
        for r in rows:
            try:
                state_data = json.loads(r["state_json"])
            except Exception:
                state_data = {}
            history.append(
                {
                    "checkpoint_id": r["id"],
                    "session_id": r["session_id"],
                    "iteration": r["iteration"],
                    "status": r["status"],
                    "message": r["message"],
                    "state": state_data,
                    "timestamp": r["timestamp"],
                }
            )
        return history

    def list_sessions(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT session_id, created_at, updated_at, final_status, total_iterations
                FROM simula_sessions
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cursor.fetchall()

        return [
            {
                "session_id": r["session_id"],
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
                "final_status": r["final_status"],
                "total_iterations": r["total_iterations"],
            }
            for r in rows
        ]

    def export_session_jsonl(self, session_id: str, output_path: str) -> str:
        history = self.get_session_history(session_id)
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)

        with open(out_file, "w", encoding="utf-8") as f:
            for entry in history:
                f.write(json.dumps(entry, default=str) + "\n")

        return str(out_file)
