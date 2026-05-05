from __future__ import annotations

import logging
import json
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Iterator
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.calendar.google_calendar_client import GoogleCalendarClient
from app.application.services.availability import AvailabilityService
from app.infrastructure.db.models.availability_rule import AvailabilityRule
from app.infrastructure.db.models.booking import Booking
from app.infrastructure.db.models.closed_date import ClosedDate
from app.infrastructure.db.models.status_history import StatusHistory
from app.infrastructure.db.models.time_block import TimeBlock
from app.infrastructure.db.models.user import User
from app.infrastructure.db.repositories.app_settings_repository import AppSettingsRepository

logger = logging.getLogger(__name__)
MSK = ZoneInfo("Europe/Moscow")


@dataclass(frozen=True)
class ClosedDayCancellation:
    booking_id: int
    user_id: int
    user_telegram_user_id: int
    topic: str | None


class AdminService:
    ACTIVE_FUTURE_STATUSES = {"pending_decision", "confirmed", "reschedule_requested"}
    ONE_TIME_WINDOWS_KEY = "one_time_windows_json"
    OVERVIEW_BOOKING_STATUSES = {"pending_decision", "confirmed", "reschedule_requested"}

    def __init__(
        self,
        session_factory: sessionmaker,
        google_service_account_file: str,
        google_calendar_id: str,
    ) -> None:
        self._session_factory = session_factory
        self._settings_repository = AppSettingsRepository()
        self._calendar_client = GoogleCalendarClient(
            service_account_file=google_service_account_file,
            calendar_id=google_calendar_id,
        )

    @contextmanager
    def _session_scope(self) -> Iterator[Session]:
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def set_working_window(self, weekday: int, start_at: time, end_at: time) -> AvailabilityRule:
        if weekday < 0 or weekday > 6:
            raise ValueError("weekday должен быть от 0 до 6.")
        if end_at <= start_at:
            raise ValueError("Время окончания должно быть позже начала.")
        with self._session_scope() as session:
            existing = (
                session.query(AvailabilityRule)
                .filter(
                    AvailabilityRule.weekday == weekday,
                    AvailabilityRule.start_time == start_at,
                    AvailabilityRule.end_time == end_at,
                    AvailabilityRule.is_active.is_(True),
                )
                .one_or_none()
            )
            if existing is not None:
                logger.info(
                    "Availability window already exists: rule_id=%s weekday=%s start=%s end=%s",
                    existing.id,
                    weekday,
                    start_at,
                    end_at,
                )
                return existing
            now = datetime.utcnow()
            rule = AvailabilityRule(
                weekday=weekday,
                start_time=start_at,
                end_time=end_at,
                is_active=True,
                created_at=now,
                updated_at=now,
            )
            session.add(rule)
            session.flush()
            logger.info(
                "Availability window added: rule_id=%s weekday=%s start=%s end=%s",
                rule.id,
                weekday,
                start_at,
                end_at,
            )
            return rule

    def remove_working_window(self, rule_id: int) -> bool:
        with self._session_scope() as session:
            row = session.query(AvailabilityRule).filter(AvailabilityRule.id == rule_id).one_or_none()
            if row is None:
                return False
            session.delete(row)
            logger.info("Availability window removed: rule_id=%s", rule_id)
            return True

    def list_working_windows(self, limit: int = 200) -> list[AvailabilityRule]:
        with self._session_scope() as session:
            rows = (
                session.query(AvailabilityRule)
                .filter(AvailabilityRule.is_active.is_(True))
                .order_by(AvailabilityRule.weekday.asc(), AvailabilityRule.start_time.asc())
                .limit(limit)
                .all()
            )
            return rows

    def clear_working_windows(self, weekday: int | None = None) -> int:
        with self._session_scope() as session:
            query = session.query(AvailabilityRule)
            if weekday is not None:
                query = query.filter(AvailabilityRule.weekday == weekday)
            count = query.delete(synchronize_session=False)
            logger.info("Availability windows cleared: weekday=%s deleted=%s", weekday, count)
            return int(count)

    def set_min_lead_minutes(self, minutes: int) -> None:
        if minutes < 0 or minutes > 10080:
            raise ValueError("MIN lead должен быть в диапазоне 0..10080 минут.")
        with self._session_scope() as session:
            self._settings_repository.set_value(session, "min_lead_minutes", str(minutes))
            logger.info("Min lead setting updated: minutes=%s", minutes)

    def add_one_time_window(
        self,
        target_date: date,
        start_at: time,
        end_at: time,
        comment: str | None = None,
    ) -> dict[str, str]:
        if end_at <= start_at:
            raise ValueError("Время окончания должно быть позже начала.")

        with self._session_scope() as session:
            raw = self._settings_repository.get_value(session, self.ONE_TIME_WINDOWS_KEY)
            items: list[dict[str, str]]
            if raw:
                try:
                    parsed = json.loads(raw)
                    items = parsed if isinstance(parsed, list) else []
                except Exception:
                    items = []
            else:
                items = []

            item = {
                "date": target_date.isoformat(),
                "start": start_at.strftime("%H:%M"),
                "end": end_at.strftime("%H:%M"),
            }
            if comment:
                item["comment"] = comment
            exists = any(
                isinstance(existing, dict)
                and existing.get("date") == item["date"]
                and existing.get("start") == item["start"]
                and existing.get("end") == item["end"]
                for existing in items
            )
            if exists:
                logger.info(
                    "One-time window already exists: date=%s start=%s end=%s",
                    target_date.isoformat(),
                    start_at,
                    end_at,
                )
                return item
            items.append(item)
            items.sort(key=lambda x: (x.get("date", ""), x.get("start", "")))
            self._settings_repository.set_value(
                session,
                self.ONE_TIME_WINDOWS_KEY,
                json.dumps(items, ensure_ascii=False),
            )
            logger.info(
                "One-time window added: date=%s start=%s end=%s",
                target_date.isoformat(),
                start_at,
                end_at,
            )
            return item

    def list_one_time_windows(self, limit: int = 100) -> list[dict[str, str]]:
        with self._session_scope() as session:
            raw = self._settings_repository.get_value(session, self.ONE_TIME_WINDOWS_KEY)
            if not raw:
                return []
            try:
                parsed = json.loads(raw)
            except Exception:
                return []
            if not isinstance(parsed, list):
                return []
            items = [x for x in parsed if isinstance(x, dict)]
            items.sort(key=lambda x: (x.get("date", ""), x.get("start", "")))
            return items[:limit]

    def remove_one_time_windows_by_date(self, target_date: date) -> int:
        with self._session_scope() as session:
            raw = self._settings_repository.get_value(session, self.ONE_TIME_WINDOWS_KEY)
            if not raw:
                return 0
            try:
                parsed = json.loads(raw)
            except Exception:
                parsed = []
            if not isinstance(parsed, list):
                parsed = []
            target = target_date.isoformat()
            before = len(parsed)
            filtered = [x for x in parsed if not (isinstance(x, dict) and x.get("date") == target)]
            deleted = before - len(filtered)
            self._settings_repository.set_value(
                session,
                self.ONE_TIME_WINDOWS_KEY,
                json.dumps(filtered, ensure_ascii=False),
            )
            logger.info("One-time windows removed by date: date=%s deleted=%s", target, deleted)
            return deleted

    def remove_one_time_window(self, *, target_date: date, start_at: time, end_at: time) -> bool:
        with self._session_scope() as session:
            raw = self._settings_repository.get_value(session, self.ONE_TIME_WINDOWS_KEY)
            if not raw:
                return False
            try:
                parsed = json.loads(raw)
            except Exception:
                parsed = []
            if not isinstance(parsed, list):
                parsed = []

            date_key = target_date.isoformat()
            start_key = start_at.strftime("%H:%M")
            end_key = end_at.strftime("%H:%M")
            removed = False
            filtered: list[dict] = []
            for row in parsed:
                if (
                    not removed
                    and isinstance(row, dict)
                    and row.get("date") == date_key
                    and row.get("start") == start_key
                    and row.get("end") == end_key
                ):
                    removed = True
                    continue
                if isinstance(row, dict):
                    filtered.append(row)

            if not removed:
                return False

            self._settings_repository.set_value(
                session,
                self.ONE_TIME_WINDOWS_KEY,
                json.dumps(filtered, ensure_ascii=False),
            )
            logger.info(
                "One-time window removed: date=%s start=%s end=%s",
                target_date.isoformat(),
                start_at,
                end_at,
            )
            return True

    def get_min_lead_minutes(self) -> int | None:
        with self._session_scope() as session:
            raw = self._settings_repository.get_value(session, "min_lead_minutes")
            if raw is None:
                return None
            try:
                return int(raw)
            except ValueError:
                return None

    def add_time_block(self, target_date: date, start_at: time, end_at: time, comment: str | None = None) -> TimeBlock:
        if end_at <= start_at:
            raise ValueError("Время окончания блока должно быть позже начала.")
        with self._session_scope() as session:
            block = TimeBlock(
                date=target_date,
                start_time=start_at,
                end_time=end_at,
                comment=comment,
                created_at=datetime.utcnow(),
            )
            session.add(block)
            session.flush()
            logger.info(
                "Time block created: block_id=%s date=%s start=%s end=%s",
                block.id,
                target_date.isoformat(),
                start_at,
                end_at,
            )
            return block

    def remove_time_block(self, block_id: int) -> bool:
        with self._session_scope() as session:
            block = session.query(TimeBlock).filter(TimeBlock.id == block_id).one_or_none()
            if block is None:
                return False
            session.delete(block)
            logger.info("Time block removed: block_id=%s date=%s", block_id, block.date.isoformat())
            return True

    def list_time_blocks(
        self,
        *,
        start_date: date,
        end_date: date,
        limit: int = 300,
    ) -> list[TimeBlock]:
        with self._session_scope() as session:
            rows = (
                session.query(TimeBlock)
                .filter(TimeBlock.date >= start_date, TimeBlock.date <= end_date)
                .order_by(TimeBlock.date.asc(), TimeBlock.start_time.asc())
                .limit(limit)
                .all()
            )
            return rows

    def close_day(self, target_date: date, reason: str | None = None) -> list[ClosedDayCancellation]:
        now_msk_naive = datetime.now(MSK).replace(tzinfo=None)
        with self._session_scope() as session:
            exists = session.query(ClosedDate).filter(ClosedDate.date == target_date).one_or_none()
            if exists is None:
                row = ClosedDate(date=target_date, reason=reason, created_at=datetime.utcnow())
                session.add(row)
                session.flush()
            logger.info("Closed date set: date=%s", target_date.isoformat())

            day_start = datetime.combine(target_date, time(0, 0))
            day_end = datetime.combine(target_date, time(23, 59, 59))
            bookings = (
                session.query(Booking, User)
                .join(User, User.id == Booking.user_id)
                .filter(
                    Booking.status.in_(self.ACTIVE_FUTURE_STATUSES),
                    Booking.slot_start_at.isnot(None),
                    Booking.slot_start_at >= now_msk_naive,
                    Booking.slot_start_at >= day_start,
                    Booking.slot_start_at <= day_end,
                )
                .all()
            )

            notifications: list[ClosedDayCancellation] = []
            for booking, user in bookings:
                if booking.calendar_event_id:
                    self._calendar_client.delete_event(booking.calendar_event_id)
                booking.previous_slot_start_at = booking.slot_start_at
                booking.previous_slot_end_at = booking.slot_end_at
                booking.slot_start_at = None
                booking.slot_end_at = None
                booking.requested_new_slot_start_at = None
                booking.requested_new_slot_end_at = None
                booking.calendar_event_id = None
                booking.expires_at = None
                old_status = booking.status
                booking.status = "canceled_by_admin"
                booking.updated_at = datetime.utcnow()
                session.add(
                    StatusHistory(
                        booking_id=booking.id,
                        old_status=old_status,
                        new_status="canceled_by_admin",
                        changed_by="admin:close_day",
                    )
                )
                notifications.append(
                    ClosedDayCancellation(
                        booking_id=booking.id,
                        user_id=user.id,
                        user_telegram_user_id=user.telegram_user_id,
                        topic=booking.topic,
                    )
                )
            logger.info(
                "Closed day processed: date=%s canceled_bookings=%s",
                target_date.isoformat(),
                len(notifications),
            )
            return notifications

    def reopen_day(self, target_date: date) -> bool:
        with self._session_scope() as session:
            row = session.query(ClosedDate).filter(ClosedDate.date == target_date).one_or_none()
            if row is None:
                return False
            session.delete(row)
            logger.info("Closed date removed (reopened): date=%s", target_date.isoformat())
            return True

    def list_closed_days(self, limit: int = 120) -> list[ClosedDate]:
        with self._session_scope() as session:
            rows = (
                session.query(ClosedDate)
                .order_by(ClosedDate.date.asc())
                .limit(limit)
                .all()
            )
            return rows

    def get_calendar_overview(self, *, start_date: date, horizon_days: int = 21) -> list[dict]:
        if horizon_days < 1 or horizon_days > 62:
            raise ValueError("horizon_days должен быть в диапазоне 1..62.")
        end_date = start_date + timedelta(days=horizon_days - 1)
        day_start = datetime.combine(start_date, time(0, 0))
        day_end = datetime.combine(end_date, time(23, 59, 59))
        windows_by_weekday_default = AvailabilityService.DEFAULT_RULES
        result: list[dict] = []

        with self._session_scope() as session:
            rules = (
                session.query(AvailabilityRule)
                .filter(AvailabilityRule.is_active.is_(True))
                .order_by(AvailabilityRule.weekday.asc(), AvailabilityRule.start_time.asc())
                .all()
            )
            closed_rows = (
                session.query(ClosedDate)
                .filter(ClosedDate.date >= start_date, ClosedDate.date <= end_date)
                .order_by(ClosedDate.date.asc())
                .all()
            )
            block_rows = (
                session.query(TimeBlock)
                .filter(TimeBlock.date >= start_date, TimeBlock.date <= end_date)
                .order_by(TimeBlock.date.asc(), TimeBlock.start_time.asc())
                .all()
            )
            bookings = (
                session.query(Booking, User)
                .join(User, User.id == Booking.user_id)
                .filter(
                    Booking.status.in_(self.OVERVIEW_BOOKING_STATUSES),
                    Booking.slot_start_at.isnot(None),
                    Booking.slot_end_at.isnot(None),
                    Booking.slot_start_at >= day_start,
                    Booking.slot_start_at <= day_end,
                )
                .order_by(Booking.slot_start_at.asc())
                .all()
            )
            one_time_windows = self._load_one_time_windows(
                session=session,
                start_date=start_date,
                end_date=end_date,
            )

        rules_by_weekday: dict[int, list[tuple[time, time]]] = {}
        if rules:
            for row in rules:
                rules_by_weekday.setdefault(row.weekday, []).append((row.start_time, row.end_time))
        else:
            rules_by_weekday = {
                weekday: list(items)
                for weekday, items in windows_by_weekday_default.items()
            }
        for weekday in rules_by_weekday:
            rules_by_weekday[weekday].sort(key=lambda x: x[0])

        closed_map = {row.date: row for row in closed_rows}
        blocks_by_date: dict[date, list[TimeBlock]] = {}
        for block in block_rows:
            blocks_by_date.setdefault(block.date, []).append(block)

        bookings_by_date: dict[date, list[tuple[Booking, User]]] = {}
        for booking, user in bookings:
            day = booking.slot_start_at.date()
            bookings_by_date.setdefault(day, []).append((booking, user))

        current = start_date
        while current <= end_date:
            weekday_windows = list(rules_by_weekday.get(current.weekday(), []))
            weekday_windows.extend(one_time_windows.get(current, []))
            weekday_windows.sort(key=lambda x: x[0])
            windows = [
                {
                    "start_time": start_at.strftime("%H:%M"),
                    "end_time": end_at.strftime("%H:%M"),
                }
                for start_at, end_at in weekday_windows
            ]
            day_blocks = blocks_by_date.get(current, [])
            day_bookings = bookings_by_date.get(current, [])
            pending_count = sum(1 for booking, _ in day_bookings if booking.status == "pending_decision")
            confirmed_count = sum(1 for booking, _ in day_bookings if booking.status == "confirmed")
            reschedule_count = sum(1 for booking, _ in day_bookings if booking.status == "reschedule_requested")
            previews = [
                {
                    "booking_id": booking.id,
                    "topic": booking.topic,
                    "status": booking.status,
                    "slot_start_at": booking.slot_start_at,
                    "slot_end_at": booking.slot_end_at,
                    "client_name": user.name or user.telegram_display_name or user.telegram_username,
                    "client_username": user.telegram_username,
                }
                for booking, user in day_bookings[:8]
            ]
            result.append(
                {
                    "date": current,
                    "is_closed": current in closed_map,
                    "closed_reason": closed_map[current].reason if current in closed_map else None,
                    "working_windows": windows,
                    "time_blocks": [
                        {
                            "block_id": block.id,
                            "start_time": block.start_time.strftime("%H:%M"),
                            "end_time": block.end_time.strftime("%H:%M"),
                            "comment": block.comment,
                        }
                        for block in day_blocks
                    ],
                    "pending_count": pending_count,
                    "confirmed_count": confirmed_count,
                    "reschedule_count": reschedule_count,
                    "bookings_preview": previews,
                }
            )
            current += timedelta(days=1)

        logger.info(
            "Admin calendar overview generated: start_date=%s horizon_days=%s rows=%s",
            start_date.isoformat(),
            horizon_days,
            len(result),
        )
        return result

    def get_availability_snapshot(self, *, from_date: date, days: int = 35) -> dict:
        if days < 1 or days > 120:
            raise ValueError("days должен быть в диапазоне 1..120.")
        to_date = from_date + timedelta(days=days - 1)
        windows = self.list_working_windows(limit=300)
        min_lead = self.get_min_lead_minutes()
        closed_days = self.list_closed_days(limit=500)
        one_time = self.list_one_time_windows(limit=500)
        blocks = self.list_time_blocks(start_date=from_date, end_date=to_date, limit=500)
        logger.info(
            "Admin availability snapshot loaded: from_date=%s to_date=%s windows=%s closed=%s blocks=%s one_time=%s",
            from_date.isoformat(),
            to_date.isoformat(),
            len(windows),
            len(closed_days),
            len(blocks),
            len(one_time),
        )
        return {
            "min_lead_minutes": min_lead,
            "working_windows": windows,
            "closed_days": [row for row in closed_days if row.date >= from_date],
            "time_blocks": blocks,
            "one_time_windows": one_time,
        }

    def search_bookings(
        self,
        status: str | None = None,
        target_date: date | None = None,
        name: str | None = None,
        email: str | None = None,
        telegram_user_id: int | None = None,
        limit: int = 50,
    ) -> list[tuple[Booking, User]]:
        with self._session_scope() as session:
            query = session.query(Booking, User).join(User, User.id == Booking.user_id)
            if status:
                query = query.filter(Booking.status == status)
            if target_date:
                day_start = datetime.combine(target_date, time(0, 0))
                day_end = datetime.combine(target_date, time(23, 59, 59))
                query = query.filter(Booking.slot_start_at.isnot(None), Booking.slot_start_at >= day_start, Booking.slot_start_at <= day_end)
            if name:
                query = query.filter(User.name.ilike(f"%{name}%"))
            if email:
                query = query.filter(User.email.ilike(f"%{email}%"))
            if telegram_user_id is not None:
                query = query.filter(User.telegram_user_id == telegram_user_id)
            rows = query.order_by(Booking.created_at.desc()).limit(limit).all()
            logger.info(
                "Booking search executed: status=%s date=%s name=%s email=%s telegram_user_id=%s count=%s",
                status,
                target_date.isoformat() if target_date else None,
                bool(name),
                bool(email),
                telegram_user_id,
                len(rows),
            )
            return rows

    def block_user(self, telegram_user_id: int) -> list[ClosedDayCancellation]:
        now_msk_naive = datetime.now(MSK).replace(tzinfo=None)
        with self._session_scope() as session:
            user = session.query(User).filter(User.telegram_user_id == telegram_user_id).one_or_none()
            if user is None:
                raise ValueError("Пользователь не найден.")
            user.is_blocked = True
            user.updated_at = datetime.utcnow()

            bookings = (
                session.query(Booking)
                .filter(
                    Booking.user_id == user.id,
                    Booking.status.in_(self.ACTIVE_FUTURE_STATUSES),
                    Booking.slot_start_at.isnot(None),
                    Booking.slot_start_at >= now_msk_naive,
                )
                .all()
            )
            notifications: list[ClosedDayCancellation] = []
            for booking in bookings:
                if booking.calendar_event_id:
                    self._calendar_client.delete_event(booking.calendar_event_id)
                booking.previous_slot_start_at = booking.slot_start_at
                booking.previous_slot_end_at = booking.slot_end_at
                booking.slot_start_at = None
                booking.slot_end_at = None
                booking.requested_new_slot_start_at = None
                booking.requested_new_slot_end_at = None
                booking.calendar_event_id = None
                booking.expires_at = None
                old_status = booking.status
                booking.status = "canceled_by_admin"
                booking.updated_at = datetime.utcnow()
                session.add(
                    StatusHistory(
                        booking_id=booking.id,
                        old_status=old_status,
                        new_status="canceled_by_admin",
                        changed_by="admin:block_user",
                    )
                )
                notifications.append(
                    ClosedDayCancellation(
                        booking_id=booking.id,
                        user_id=user.id,
                        user_telegram_user_id=user.telegram_user_id,
                        topic=booking.topic,
                    )
                )
            logger.info(
                "User blocked and future bookings canceled: telegram_user_id=%s canceled=%s",
                telegram_user_id,
                len(notifications),
            )
            return notifications

    def unblock_user(self, telegram_user_id: int) -> None:
        with self._session_scope() as session:
            user = session.query(User).filter(User.telegram_user_id == telegram_user_id).one_or_none()
            if user is None:
                raise ValueError("Пользователь не найден.")
            user.is_blocked = False
            user.updated_at = datetime.utcnow()
            logger.info("User unblocked: telegram_user_id=%s", telegram_user_id)

    def _load_one_time_windows(
        self,
        *,
        session: Session,
        start_date: date,
        end_date: date,
    ) -> dict[date, list[tuple[time, time]]]:
        raw = self._settings_repository.get_value(session, self.ONE_TIME_WINDOWS_KEY)
        if not raw:
            return {}
        try:
            rows = json.loads(raw)
        except Exception:
            return {}
        if not isinstance(rows, list):
            return {}
        result: dict[date, list[tuple[time, time]]] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            date_raw = str(row.get("date", ""))
            start_raw = str(row.get("start", ""))
            end_raw = str(row.get("end", ""))
            try:
                day = datetime.strptime(date_raw, "%Y-%m-%d").date()
                start_at = datetime.strptime(start_raw, "%H:%M").time()
                end_at = datetime.strptime(end_raw, "%H:%M").time()
            except ValueError:
                continue
            if day < start_date or day > end_date or end_at <= start_at:
                continue
            result.setdefault(day, []).append((start_at, end_at))
        for day, values in result.items():
            values.sort(key=lambda x: x[0])
            result[day] = values
        return result
