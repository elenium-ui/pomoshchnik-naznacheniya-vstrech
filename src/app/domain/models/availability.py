from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Slot:
    start_at: datetime
    end_at: datetime


@dataclass(frozen=True)
class TimeInterval:
    start_at: datetime
    end_at: datetime
    source: str


def intervals_overlap(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    return a_start < b_end and b_start < a_end
