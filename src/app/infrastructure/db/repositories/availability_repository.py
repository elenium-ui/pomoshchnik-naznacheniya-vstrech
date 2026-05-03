from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.infrastructure.db.models.availability_rule import AvailabilityRule
from app.infrastructure.db.models.booking import Booking
from app.infrastructure.db.models.closed_date import ClosedDate
from app.infrastructure.db.models.time_block import TimeBlock


class AvailabilityRepository:
    OCCUPYING_STATUSES = {
        "pending_decision",
        "confirmed",
        "reschedule_requested",
        "draft",
    }

    def get_active_rules(self, session: Session) -> list[AvailabilityRule]:
        return (
            session.query(AvailabilityRule)
            .filter(AvailabilityRule.is_active.is_(True))
            .order_by(AvailabilityRule.weekday.asc(), AvailabilityRule.start_time.asc())
            .all()
        )

    def get_closed_dates(self, session: Session, start_date: date, end_date: date) -> set[date]:
        rows = (
            session.query(ClosedDate.date)
            .filter(ClosedDate.date >= start_date, ClosedDate.date <= end_date)
            .all()
        )
        return {row[0] for row in rows}

    def get_time_blocks(self, session: Session, start_date: date, end_date: date) -> list[TimeBlock]:
        return (
            session.query(TimeBlock)
            .filter(TimeBlock.date >= start_date, TimeBlock.date <= end_date)
            .order_by(TimeBlock.date.asc(), TimeBlock.start_time.asc())
            .all()
        )

    def get_occupied_bookings(
        self,
        session: Session,
        start_at: datetime,
        end_at: datetime,
    ) -> list[Booking]:
        return (
            session.query(Booking)
            .filter(
                Booking.status.in_(self.OCCUPYING_STATUSES),
                or_(
                    and_(
                        Booking.slot_start_at.isnot(None),
                        Booking.slot_end_at.isnot(None),
                        Booking.slot_start_at < end_at,
                        Booking.slot_end_at > start_at,
                    ),
                    and_(
                        Booking.status == "reschedule_requested",
                        Booking.requested_new_slot_start_at.isnot(None),
                        Booking.requested_new_slot_end_at.isnot(None),
                        Booking.requested_new_slot_start_at < end_at,
                        Booking.requested_new_slot_end_at > start_at,
                    ),
                ),
            )
            .order_by(Booking.slot_start_at.asc())
            .all()
        )
