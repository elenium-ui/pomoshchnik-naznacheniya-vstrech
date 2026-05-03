from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session


class AppSettingsRepository:
    TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS app_settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """

    def ensure_table(self, session: Session) -> None:
        session.execute(text(self.TABLE_SQL))

    def get_value(self, session: Session, key: str) -> str | None:
        self.ensure_table(session)
        row = session.execute(text("SELECT value FROM app_settings WHERE key = :key"), {"key": key}).first()
        return None if row is None else str(row[0])

    def set_value(self, session: Session, key: str, value: str) -> None:
        self.ensure_table(session)
        session.execute(
            text(
                """
                INSERT INTO app_settings(key, value)
                VALUES(:key, :value)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """
            ),
            {"key": key, "value": value},
        )
