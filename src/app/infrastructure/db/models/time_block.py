from datetime import date as dt_date
from datetime import datetime
from datetime import time as dt_time
from typing import Optional

from sqlalchemy import Date, DateTime, String, Time
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base


class TimeBlock(Base):
    __tablename__ = "time_blocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[dt_date] = mapped_column(Date, index=True)
    start_time: Mapped[dt_time] = mapped_column(Time)
    end_time: Mapped[dt_time] = mapped_column(Time)
    comment: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
