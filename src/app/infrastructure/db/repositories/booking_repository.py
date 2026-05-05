from __future__ import annotations

from datetime import date, datetime, time
from typing import Optional

from sqlalchemy import and_, case, or_
from sqlalchemy.orm import Session

from app.infrastructure.db.models.booking import Booking
from app.infrastructure.db.models.user import User


class BookingRepository:
    ACTIVE_STATUSES = {
        "draft",
        "pending_decision",
        "confirmed",
        "reschedule_requested",
    }

    FUTURE_LIMIT_STATUSES = {
        "pending_decision",
        "confirmed",
        "reschedule_requested",
    }

    SLOT_OCCUPYING_STATUSES = {
        "pending_decision",
        "confirmed",
        "reschedule_requested",
    }

    def create_draft(self, session: Session, user_id: int) -> Booking:
        now = datetime.utcnow()
        booking = Booking(
            user_id=user_id,
            status="draft",
            created_at=now,
            updated_at=now,
        )
        session.add(booking)
        session.flush()
        return booking

    def get_by_id_for_user(self, session: Session, booking_id: int, user_id: int) -> Optional[Booking]:
        return (
            session.query(Booking)
            .filter(Booking.id == booking_id, Booking.user_id == user_id)
            .one_or_none()
        )

    def get_by_id(self, session: Session, booking_id: int) -> Optional[Booking]:
        return session.query(Booking).filter(Booking.id == booking_id).one_or_none()

    def update_fields(self, booking: Booking, **fields) -> Booking:
        for key, value in fields.items():
            setattr(booking, key, value)
        booking.updated_at = datetime.utcnow()
        return booking

    def list_active_by_user(
        self,
        session: Session,
        user_id: int,
        now_msk_naive: datetime | None = None,
        limit: int = 20,
    ) -> list[Booking]:
        query = session.query(Booking).filter(
            Booking.user_id == user_id,
            Booking.status.in_(self.ACTIVE_STATUSES),
        )
        if now_msk_naive is not None:
            query = query.filter(
                or_(
                    Booking.status != "confirmed",
                    Booking.slot_end_at.is_(None),
                    Booking.slot_end_at >= now_msk_naive,
                )
            )
        return query.order_by(Booking.created_at.desc()).limit(limit).all()

    def list_history_completed_by_user(
        self,
        session: Session,
        user_id: int,
        now_msk_naive: datetime,
        limit: int = 30,
    ) -> list[Booking]:
        return (
            session.query(Booking)
            .filter(
                Booking.user_id == user_id,
                Booking.status == "confirmed",
                Booking.slot_end_at.isnot(None),
                Booking.slot_end_at < now_msk_naive,
            )
            .order_by(Booking.slot_end_at.desc(), Booking.updated_at.desc())
            .limit(limit)
            .all()
        )

    def list_pending_decision(self, session: Session, limit: int = 20) -> list[Booking]:
        return (
            session.query(Booking)
            .filter(Booking.status == "pending_decision")
            .order_by(Booking.created_at.desc())
            .limit(limit)
            .all()
        )

    def list_admin_queue(self, session: Session, limit: int = 50) -> list[Booking]:
        return (
            session.query(Booking)
            .filter(Booking.status.in_(["pending_decision", "reschedule_requested"]))
            .order_by(Booking.created_at.desc())
            .limit(limit)
            .all()
        )

    def list_confirmed(self, session: Session, limit: int = 50) -> list[Booking]:
        return (
            session.query(Booking)
            .filter(Booking.status == "confirmed")
            .order_by(Booking.updated_at.desc(), Booking.created_at.desc())
            .limit(limit)
            .all()
        )

    def get_by_id_with_user(self, session: Session, booking_id: int) -> Optional[tuple[Booking, User]]:
        return (
            session.query(Booking, User)
            .join(User, User.id == Booking.user_id)
            .filter(Booking.id == booking_id)
            .one_or_none()
        )

    def search_for_admin(
        self,
        session: Session,
        *,
        status: str | None = None,
        target_date: date | None = None,
        search: str | None = None,
        limit: int = 50,
    ) -> list[tuple[Booking, User]]:
        query = session.query(Booking, User).join(User, User.id == Booking.user_id)
        if status:
            query = query.filter(Booking.status == status)
        if target_date:
            day_start = datetime.combine(target_date, time(0, 0))
            day_end = datetime.combine(target_date, time(23, 59, 59))
            query = query.filter(Booking.slot_start_at.isnot(None), Booking.slot_start_at >= day_start, Booking.slot_start_at <= day_end)
        if search:
            like = f"%{search.strip()}%"
            query = query.filter(
                or_(
                    Booking.topic.ilike(like),
                    User.name.ilike(like),
                    User.email.ilike(like),
                    User.telegram_username.ilike(like),
                )
            )
        priority = case(
            (
                Booking.status.in_(["pending_decision", "reschedule_requested"]),
                0,
            ),
            else_=1,
        )
        effective_slot_start = case(
            (Booking.status == "reschedule_requested", Booking.requested_new_slot_start_at),
            else_=Booking.slot_start_at,
        )
        return (
            query.order_by(
                priority.asc(),
                effective_slot_start.is_(None),
                effective_slot_start.asc(),
                Booking.created_at.desc(),
            )
            .limit(limit)
            .all()
        )

    def count_future_active_for_limit(self, session: Session, user_id: int, now_msk_naive: datetime) -> int:
        # Future bookings that must be counted for the user quota (7).
        return (
            session.query(Booking)
            .filter(
                Booking.user_id == user_id,
                Booking.status.in_(self.FUTURE_LIMIT_STATUSES),
                Booking.slot_start_at.isnot(None),
                Booking.slot_start_at >= now_msk_naive,
            )
            .count()
        )

    def has_slot_conflict(
        self,
        session: Session,
        slot_start_at: datetime,
        slot_end_at: datetime,
        exclude_booking_id: int | None = None,
    ) -> bool:
        query = session.query(Booking).filter(
            Booking.status.in_(self.SLOT_OCCUPYING_STATUSES),
            or_(
                and_(
                    Booking.slot_start_at.isnot(None),
                    Booking.slot_end_at.isnot(None),
                    Booking.slot_start_at < slot_end_at,
                    Booking.slot_end_at > slot_start_at,
                ),
                and_(
                    Booking.status == "reschedule_requested",
                    Booking.requested_new_slot_start_at.isnot(None),
                    Booking.requested_new_slot_end_at.isnot(None),
                    Booking.requested_new_slot_start_at < slot_end_at,
                    Booking.requested_new_slot_end_at > slot_start_at,
                ),
            ),
        )
        if exclude_booking_id is not None:
            query = query.filter(Booking.id != exclude_booking_id)
        return session.query(query.exists()).scalar()

    def list_expired_pending_decision(
        self,
        session: Session,
        now_msk_naive: datetime,
        limit: int = 200,
    ) -> list[Booking]:
        return (
            session.query(Booking)
            .filter(
                Booking.status == "pending_decision",
                Booking.expires_at.isnot(None),
                Booking.expires_at <= now_msk_naive,
            )
            .order_by(Booking.expires_at.asc(), Booking.id.asc())
            .limit(limit)
            .all()
        )
