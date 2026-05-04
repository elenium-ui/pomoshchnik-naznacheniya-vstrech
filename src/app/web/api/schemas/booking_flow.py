from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class InitDataPayload(BaseModel):
    init_data: str = Field(min_length=1)


class StartBookingSessionResponse(BaseModel):
    booking_id: int
    future_active_count: int
    future_active_limit: int
    profile: "BookingProfilePayload"


class BookingProfilePayload(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    telegram_username: Optional[str] = None


class SaveBookingDraftRequest(BaseModel):
    init_data: str = Field(min_length=1)
    name: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    meeting_format: str = Field(min_length=1)
    duration_minutes: int
    email: Optional[str] = None
    phone: Optional[str] = None
    comment: Optional[str] = None


class SaveBookingDraftResponse(BaseModel):
    booking_id: int
    status: str
    duration_minutes: int
    profile: BookingProfilePayload


class SlotOption(BaseModel):
    label: str
    key: str


class SlotTimeOption(BaseModel):
    label: str
    slot_key: str
    starts_at: datetime
    ends_at: datetime


class BookingSlotsResponse(BaseModel):
    total_slots: int
    non_empty_days: int
    week_options: List[SlotOption]
    day_options_by_week: Dict[str, List[SlotOption]]
    time_options_by_day: Dict[str, List[SlotTimeOption]]


class SubmitBookingRequest(BaseModel):
    init_data: str = Field(min_length=1)
    slot_key: str = Field(min_length=1)


class SubmittedBookingPayload(BaseModel):
    booking_id: int
    status: str
    topic: Optional[str] = None
    meeting_format: Optional[str] = None
    duration_minutes: Optional[int] = None
    comment: Optional[str] = None
    slot_start_at: datetime
    slot_end_at: datetime

