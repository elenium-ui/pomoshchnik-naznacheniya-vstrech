from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)


class CalendarIntegrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class CalendarEventRequest:
    summary: str
    description: str
    start_at: datetime
    end_at: datetime
    timezone: str
    attendee_email: str | None = None


class CalendarClient(Protocol):
    def create_event(self, request: CalendarEventRequest) -> str:
        """Create calendar event and return provider event id."""

    def delete_event(self, event_id: str) -> None:
        """Delete calendar event by provider event id."""

    def update_event(self, event_id: str, request: CalendarEventRequest) -> None:
        """Update existing calendar event."""


class GoogleCalendarClient:
    SCOPE = "https://www.googleapis.com/auth/calendar"

    def __init__(self, service_account_file: str, calendar_id: str) -> None:
        self._service_account_file = service_account_file
        self._calendar_id = calendar_id

    def create_event(self, request: CalendarEventRequest) -> str:
        logger.info(
            "Google Calendar API call: create_event calendar_id=%s start=%s end=%s attendee=%s",
            self._calendar_id,
            request.start_at.isoformat(),
            request.end_at.isoformat(),
            bool(request.attendee_email),
        )

        service = self._build_service()
        body = {
            "summary": request.summary,
            "description": request.description,
            "start": {
                "dateTime": request.start_at.isoformat(),
                "timeZone": request.timezone,
            },
            "end": {
                "dateTime": request.end_at.isoformat(),
                "timeZone": request.timezone,
            },
        }

        if request.attendee_email:
            body["attendees"] = [{"email": request.attendee_email}]

        try:
            result = self._insert_event(service=service, body=body, send_updates="all")
        except Exception as exc:
            if request.attendee_email and self._is_forbidden_service_account_attendees(exc):
                logger.warning(
                    "Google Calendar service account cannot invite attendees without DWD. "
                    "Retrying event create without attendees."
                )
                fallback_body = dict(body)
                fallback_body.pop("attendees", None)
                try:
                    result = self._insert_event(service=service, body=fallback_body, send_updates="none")
                except Exception as fallback_exc:
                    logger.exception("Google Calendar API create_event fallback failed.")
                    raise CalendarIntegrationError("Не удалось создать событие в Google Calendar.") from fallback_exc
            else:
                logger.exception("Google Calendar API create_event failed.")
                raise CalendarIntegrationError("Не удалось создать событие в Google Calendar.") from exc

        event_id = result.get("id")
        if not event_id:
            logger.error("Google Calendar API returned event without id.")
            raise CalendarIntegrationError("Google Calendar вернул событие без id.")

        logger.info("Google Calendar event created: event_id=%s", event_id)
        return str(event_id)

    def delete_event(self, event_id: str) -> None:
        logger.info(
            "Google Calendar API call: delete_event calendar_id=%s event_id=%s",
            self._calendar_id,
            event_id,
        )
        service = self._build_service()
        try:
            service.events().delete(calendarId=self._calendar_id, eventId=event_id, sendUpdates="all").execute()
            logger.info("Google Calendar event deleted: event_id=%s", event_id)
        except Exception as exc:
            logger.exception("Google Calendar API delete_event failed: event_id=%s", event_id)
            raise CalendarIntegrationError("Не удалось удалить событие из Google Calendar.") from exc

    def update_event(self, event_id: str, request: CalendarEventRequest) -> None:
        logger.info(
            "Google Calendar API call: update_event calendar_id=%s event_id=%s",
            self._calendar_id,
            event_id,
        )
        service = self._build_service()
        body = {
            "summary": request.summary,
            "description": request.description,
            "start": {
                "dateTime": request.start_at.isoformat(),
                "timeZone": request.timezone,
            },
            "end": {
                "dateTime": request.end_at.isoformat(),
                "timeZone": request.timezone,
            },
        }
        if request.attendee_email:
            body["attendees"] = [{"email": request.attendee_email}]
        try:
            self._patch_event(
                service=service,
                event_id=event_id,
                body=body,
                send_updates="all",
            )
            logger.info("Google Calendar event updated: event_id=%s", event_id)
        except Exception as exc:
            if request.attendee_email and self._is_forbidden_service_account_attendees(exc):
                logger.warning(
                    "Google Calendar service account cannot invite attendees without DWD. "
                    "Retrying event update without attendees."
                )
                fallback_body = dict(body)
                fallback_body.pop("attendees", None)
                try:
                    self._patch_event(
                        service=service,
                        event_id=event_id,
                        body=fallback_body,
                        send_updates="none",
                    )
                    logger.info("Google Calendar event updated via fallback: event_id=%s", event_id)
                    return
                except Exception as fallback_exc:
                    logger.exception("Google Calendar API update_event fallback failed: event_id=%s", event_id)
                    raise CalendarIntegrationError("Не удалось обновить событие в Google Calendar.") from fallback_exc
            logger.exception("Google Calendar API update_event failed: event_id=%s", event_id)
            raise CalendarIntegrationError("Не удалось обновить событие в Google Calendar.") from exc

    def _insert_event(self, service, body: dict, send_updates: str):
        return (
            service.events()
            .insert(
                calendarId=self._calendar_id,
                body=body,
                sendUpdates=send_updates,
            )
            .execute()
        )

    def _patch_event(self, service, event_id: str, body: dict, send_updates: str) -> None:
        service.events().patch(
            calendarId=self._calendar_id,
            eventId=event_id,
            body=body,
            sendUpdates=send_updates,
        ).execute()

    @staticmethod
    def _is_forbidden_service_account_attendees(exc: Exception) -> bool:
        message = str(exc).lower()
        return (
            "forbiddenforserviceaccounts" in message
            or "service accounts cannot invite attendees" in message
        )

    def _build_service(self):
        if not Path(self._service_account_file).exists():
            raise CalendarIntegrationError(
                "Файл service account не найден. Проверьте GOOGLE_SERVICE_ACCOUNT_FILE."
            )
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise CalendarIntegrationError(
                "Не установлены зависимости Google API. Установите google-api-python-client и google-auth."
            ) from exc

        credentials = service_account.Credentials.from_service_account_file(
            self._service_account_file,
            scopes=[self.SCOPE],
        )
        return build("calendar", "v3", credentials=credentials, cache_discovery=False)
