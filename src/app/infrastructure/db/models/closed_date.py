from datetime import date as dt_date
from datetime import datetime
from typing import Optional

from sqlalchemy import Date, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base


class ClosedDate(Base):
    __tablename__ = "closed_dates"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[dt_date] = mapped_column(Date, unique=True, index=True)
    reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
