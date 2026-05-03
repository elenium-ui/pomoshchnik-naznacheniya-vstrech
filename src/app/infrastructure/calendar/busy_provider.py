from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.domain.models.availability import TimeInterval


class BusyIntervalProvider(Protocol):
    def get_busy_intervals(self, start_at: datetime, end_at: datetime) -> list[TimeInterval]:
        """Return busy intervals from external systems (e.g., Google Calendar)."""


class NullBusyIntervalProvider:
    def get_busy_intervals(self, start_at: datetime, end_at: datetime) -> list[TimeInterval]:
        return []
