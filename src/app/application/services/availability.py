from __future__ import annotations

import logging
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import sessionmaker

from app.domain.models.availability import Slot, TimeInterval, intervals_overlap
from app.infrastructure.calendar.busy_provider import BusyIntervalProvider, NullBusyIntervalProvider
from app.infrastructure.db.repositories.app_settings_repository import AppSettingsRepository
from app.infrastructure.db.repositories.availability_repository import AvailabilityRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AvailabilityPolicy:
    timezone: str = "Europe/Moscow"
    slot_step_minutes: int = 30
    horizon_days: int = 35
    min_lead_minutes: int = 60
    daily_limit: int = 4


class AvailabilityService:
    DEFAULT_RULES = {
        0: [(time(10, 0), time(12, 0)), (time(14, 0), time(16, 0))],
        1: [(time(10, 0), time(12, 0)), (time(14, 0), time(16, 0))],
        2: [(time(10, 0), time(12, 0)), (time(14, 0), time(16, 0))],
        3: [(time(10, 0), time(12, 0)), (time(14, 0), time(16, 0))],
        4: [(time(10, 0), time(12, 0)), (time(14, 0), time(16, 0))],
    }

    def __init__(
        self,
        session_factory: sessionmaker,
        policy: AvailabilityPolicy | None = None,
        repository: AvailabilityRepository | None = None,
        busy_provider: BusyIntervalProvider | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._policy = policy or AvailabilityPolicy()
        self._repository = repository or AvailabilityRepository()
        self._settings_repository = AppSettingsRepository()
        self._busy_provider = busy_provider or NullBusyIntervalProvider()
        self._tz = ZoneInfo(self._policy.timezone)

    def get_available_slots(
        self,
        duration_minutes: int,
        now: datetime | None = None,
    ) -> dict[date, list[Slot]]:
        now_msk = self._to_msk(now or datetime.now(self._tz))
        min_lead_minutes = self._load_min_lead_minutes()
        start_threshold = self._ceil_to_step(now_msk + timedelta(minutes=min_lead_minutes))

        start_date = now_msk.date()
        end_date = start_date + timedelta(days=self._policy.horizon_days)
        range_start = datetime.combine(start_date, time(0, 0), tzinfo=self._tz)
        range_end = datetime.combine(end_date + timedelta(days=1), time(0, 0), tzinfo=self._tz)

        with self._session_factory() as session:
            rules = self._repository.get_active_rules(session)
            closed_dates = self._repository.get_closed_dates(session, start_date, end_date)
            time_blocks = self._repository.get_time_blocks(session, start_date, end_date)
            occupied_bookings = self._repository.get_occupied_bookings(session, range_start, range_end)
            one_time_windows = self._load_one_time_windows(session, start_date=start_date, end_date=end_date)

        windows_by_weekday = self._rules_to_windows(rules)
        occupied_intervals = self._occupied_intervals_from_bookings(occupied_bookings)
        blocked_intervals = occupied_intervals + self._time_block_intervals(time_blocks)

        external_busy = [self._normalize_interval(iv) for iv in self._busy_provider.get_busy_intervals(range_start, range_end)]
        blocked_intervals.extend(external_busy)

        occupied_count_by_day = self._count_occupied_by_day(occupied_intervals)
        slots_by_date: dict[date, list[Slot]] = {}

        day = start_date
        while day <= end_date:
            if day in closed_dates:
                logger.info("Slot day excluded: %s reason=closed_date", day.isoformat())
                day += timedelta(days=1)
                continue

            weekday_windows = list(windows_by_weekday.get(day.weekday(), []))
            weekday_windows.extend(one_time_windows.get(day, []))
            weekday_windows.sort(key=lambda item: item[0])
            if not weekday_windows:
                logger.info("Slot day excluded: %s reason=no_working_windows", day.isoformat())
                day += timedelta(days=1)
                continue

            occupied_count = occupied_count_by_day.get(day, 0)
            if occupied_count >= self._policy.daily_limit:
                logger.info(
                    "Slot day excluded: %s reason=daily_limit occupied=%s limit=%s",
                    day.isoformat(),
                    occupied_count,
                    self._policy.daily_limit,
                )
                day += timedelta(days=1)
                continue

            day_slots, excluded = self._build_day_slots(
                day=day,
                duration_minutes=duration_minutes,
                windows=weekday_windows,
                blocked_intervals=blocked_intervals,
                start_threshold=start_threshold,
            )

            if excluded:
                logger.info(
                    "Slot exclusions for %s: lead_time=%s blocked=%s",
                    day.isoformat(),
                    excluded.get("lead_time", 0),
                    excluded.get("blocked", 0),
                )

            slots_by_date[day] = day_slots
            day += timedelta(days=1)

        return slots_by_date

    def _build_day_slots(
        self,
        day: date,
        duration_minutes: int,
        windows: list[tuple[time, time]],
        blocked_intervals: list[TimeInterval],
        start_threshold: datetime,
    ) -> tuple[list[Slot], dict[str, int]]:
        slots: list[Slot] = []
        excluded_reasons: dict[str, int] = defaultdict(int)
        duration = timedelta(minutes=duration_minutes)
        step = timedelta(minutes=self._policy.slot_step_minutes)

        for start_time, end_time in windows:
            window_start = datetime.combine(day, start_time, tzinfo=self._tz)
            window_end = datetime.combine(day, end_time, tzinfo=self._tz)
            slot_start = self._ceil_to_step(window_start)

            while slot_start + duration <= window_end:
                slot_end = slot_start + duration

                if slot_start < start_threshold:
                    excluded_reasons["lead_time"] += 1
                    logger.debug(
                        "Slot excluded: %s-%s reason=lead_time threshold=%s",
                        slot_start.isoformat(),
                        slot_end.isoformat(),
                        start_threshold.isoformat(),
                    )
                    slot_start += step
                    continue

                if self._is_blocked(slot_start, slot_end, blocked_intervals):
                    excluded_reasons["blocked"] += 1
                    logger.debug(
                        "Slot excluded: %s-%s reason=blocked",
                        slot_start.isoformat(),
                        slot_end.isoformat(),
                    )
                    slot_start += step
                    continue

                slots.append(Slot(start_at=slot_start, end_at=slot_end))
                slot_start += step

        return slots, excluded_reasons

    def _is_blocked(self, start_at: datetime, end_at: datetime, intervals: list[TimeInterval]) -> bool:
        for interval in intervals:
            if intervals_overlap(start_at, end_at, interval.start_at, interval.end_at):
                return True
        return False

    def _rules_to_windows(self, rules) -> dict[int, list[tuple[time, time]]]:
        if not rules:
            return {k: list(v) for k, v in self.DEFAULT_RULES.items()}

        windows: dict[int, list[tuple[time, time]]] = {
            weekday: list(items) for weekday, items in self.DEFAULT_RULES.items()
        }
        custom_by_weekday: dict[int, list[tuple[time, time]]] = defaultdict(list)
        for rule in rules:
            custom_by_weekday[rule.weekday].append((rule.start_time, rule.end_time))

        for weekday, items in custom_by_weekday.items():
            items.sort(key=lambda item: item[0])
            windows[weekday] = items
        return dict(windows)

    def _occupied_intervals_from_bookings(self, bookings) -> list[TimeInterval]:
        result: list[TimeInterval] = []
        for booking in bookings:
            if booking.slot_start_at and booking.slot_end_at:
                result.append(
                    TimeInterval(
                        start_at=self._to_msk(booking.slot_start_at),
                        end_at=self._to_msk(booking.slot_end_at),
                        source=f"booking:{booking.id}:{booking.status}",
                    )
                )
            if (
                booking.status == "reschedule_requested"
                and booking.requested_new_slot_start_at
                and booking.requested_new_slot_end_at
            ):
                result.append(
                    TimeInterval(
                        start_at=self._to_msk(booking.requested_new_slot_start_at),
                        end_at=self._to_msk(booking.requested_new_slot_end_at),
                        source=f"booking_reschedule_hold:{booking.id}:{booking.status}",
                    )
                )
        return result

    def _time_block_intervals(self, blocks) -> list[TimeInterval]:
        result: list[TimeInterval] = []
        for block in blocks:
            start_at = datetime.combine(block.date, block.start_time, tzinfo=self._tz)
            end_at = datetime.combine(block.date, block.end_time, tzinfo=self._tz)
            result.append(TimeInterval(start_at=start_at, end_at=end_at, source=f"time_block:{block.id}"))
        return result

    def _count_occupied_by_day(self, intervals: list[TimeInterval]) -> dict[date, int]:
        counts: dict[date, int] = defaultdict(int)
        for interval in intervals:
            counts[interval.start_at.date()] += 1
        return dict(counts)

    def _ceil_to_step(self, dt_value: datetime) -> datetime:
        dt_value = dt_value.replace(second=0, microsecond=0)
        minute = dt_value.minute
        step = self._policy.slot_step_minutes
        rem = minute % step
        if rem == 0:
            return dt_value
        return dt_value + timedelta(minutes=step - rem)

    def _to_msk(self, dt_value: datetime) -> datetime:
        if dt_value.tzinfo is None:
            return dt_value.replace(tzinfo=self._tz)
        return dt_value.astimezone(self._tz)

    def _normalize_interval(self, interval: TimeInterval) -> TimeInterval:
        return TimeInterval(
            start_at=self._to_msk(interval.start_at),
            end_at=self._to_msk(interval.end_at),
            source=interval.source,
        )

    def _load_min_lead_minutes(self) -> int:
        with self._session_factory() as session:
            raw = self._settings_repository.get_value(session, "min_lead_minutes")
        if raw is None:
            return self._policy.min_lead_minutes
        try:
            parsed = int(raw)
            if parsed < 0:
                return self._policy.min_lead_minutes
            return parsed
        except ValueError:
            return self._policy.min_lead_minutes

    def _load_one_time_windows(
        self,
        session,
        *,
        start_date: date,
        end_date: date,
    ) -> dict[date, list[tuple[time, time]]]:
        raw = self._settings_repository.get_value(session, "one_time_windows_json")
        if not raw:
            return {}
        try:
            rows = json.loads(raw)
        except Exception:
            logger.warning("Failed to parse one_time_windows_json.")
            return {}
        if not isinstance(rows, list):
            return {}

        result: dict[date, list[tuple[time, time]]] = defaultdict(list)
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                day = datetime.strptime(str(row.get("date", "")), "%Y-%m-%d").date()
                if day < start_date or day > end_date:
                    continue
                start_at = datetime.strptime(str(row.get("start", "")), "%H:%M").time()
                end_at = datetime.strptime(str(row.get("end", "")), "%H:%M").time()
            except Exception:
                continue
            if end_at <= start_at:
                continue
            result[day].append((start_at, end_at))
        return dict(result)
