from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.web.api.schemas.booking_flow import BookingSlotsResponse


class InitDataQueryPayload(BaseModel):
    init_data: str = Field(min_length=1)


class ClientBookingItem(BaseModel):
    booking_id: int
    status: str
    topic: Optional[str] = None
    meeting_format: Optional[str] = None
    duration_minutes: Optional[int] = None
    slot_start_at: Optional[datetime] = None
    slot_end_at: Optional[datetime] = None
    comment: Optional[str] = None
    calendar_event_id: Optional[str] = None
    updated_at: datetime


class ClientBookingsListResponse(BaseModel):
    items: List[ClientBookingItem]


class ClientBookingActionRequest(BaseModel):
    init_data: str = Field(min_length=1)


class ClientBookingActionResponse(BaseModel):
    booking_id: int
    status: str
    message: str


class ClientRescheduleStartResponse(BaseModel):
    booking_id: int
    status: str
    duration_minutes: int
    current_slot_start_at: datetime
    current_slot_end_at: datetime
    available_slots: BookingSlotsResponse
    message: str


class ClientProfilePayload(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    telegram_username: Optional[str] = None
    reminder_supported: bool = False
    reminder_enabled: Optional[bool] = None


class ClientProfileResponse(BaseModel):
    profile: ClientProfilePayload


class ClientProfileUpdateRequest(BaseModel):
    init_data: str = Field(min_length=1)
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    reminder_enabled: Optional[bool] = None
