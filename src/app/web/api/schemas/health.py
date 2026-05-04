from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    service: str
    timestamp_utc: datetime


class SmokeResponse(BaseModel):
    status: str
    message: str

