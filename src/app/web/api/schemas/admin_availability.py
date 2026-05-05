from __future__ import annotations

from datetime import date, datetime, time
from typing import Optional

from pydantic import BaseModel, Field


class AdminWorkingWindowPayload(BaseModel):
    rule_id: int
    weekday: int
    start_time: time
    end_time: time


class AdminTimeBlockPayload(BaseModel):
    block_id: int
    date: date
    start_time: time
    end_time: time
    comment: Optional[str] = None


class AdminOneTimeWindowPayload(BaseModel):
    date: date
    start_time: time
    end_time: time
    comment: Optional[str] = None


class AdminWindowSpanPayload(BaseModel):
    start_time: time
    end_time: time


class AdminClosedDayPayload(BaseModel):
    date: date
    reason: Optional[str] = None


class AdminCalendarBookingPreviewPayload(BaseModel):
    booking_id: int
    topic: Optional[str] = None
    status: str
    slot_start_at: datetime
    slot_end_at: datetime
    client_name: Optional[str] = None
    client_username: Optional[str] = None


class AdminCalendarDayPayload(BaseModel):
    date: date
    is_closed: bool
    closed_reason: Optional[str] = None
    working_windows: list[AdminWindowSpanPayload]
    time_blocks: list[AdminTimeBlockPayload]
    pending_count: int
    confirmed_count: int
    reschedule_count: int
    bookings_preview: list[AdminCalendarBookingPreviewPayload]


class AdminCalendarOverviewResponse(BaseModel):
    items: list[AdminCalendarDayPayload]


class AdminAvailabilitySettingsResponse(BaseModel):
    min_lead_minutes: Optional[int] = None
    working_windows: list[AdminWorkingWindowPayload]
    closed_days: list[AdminClosedDayPayload]
    time_blocks: list[AdminTimeBlockPayload]
    one_time_windows: list[AdminOneTimeWindowPayload]


class AdminSettingsMessageResponse(BaseModel):
    message: str


class AdminWorkingWindowUpsertRequest(BaseModel):
    init_data: str = Field(min_length=1)
    weekday: int = Field(ge=0, le=6)
    start_time: time
    end_time: time


class AdminWorkingWindowClearRequest(BaseModel):
    init_data: str = Field(min_length=1)
    weekday: Optional[int] = Field(default=None, ge=0, le=6)


class AdminWorkingWindowDeleteRequest(BaseModel):
    init_data: str = Field(min_length=1)
    rule_id: int = Field(ge=1)


class AdminMinLeadUpdateRequest(BaseModel):
    init_data: str = Field(min_length=1)
    minutes: int = Field(ge=0, le=10080)


class AdminClosedDayUpdateRequest(BaseModel):
    init_data: str = Field(min_length=1)
    date: date
    reason: Optional[str] = None


class AdminTimeBlockCreateRequest(BaseModel):
    init_data: str = Field(min_length=1)
    date: date
    start_time: time
    end_time: time
    comment: Optional[str] = None


class AdminTimeBlockDeleteRequest(BaseModel):
    init_data: str = Field(min_length=1)
    block_id: int = Field(ge=1)


class AdminOneTimeWindowCreateRequest(BaseModel):
    init_data: str = Field(min_length=1)
    date: date
    start_time: time
    end_time: time
    comment: Optional[str] = None


class AdminOneTimeWindowDeleteByDateRequest(BaseModel):
    init_data: str = Field(min_length=1)
    date: date


class AdminOneTimeWindowDeleteRequest(BaseModel):
    init_data: str = Field(min_length=1)
    date: date
    start_time: time
    end_time: time
