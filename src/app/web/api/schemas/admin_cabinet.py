from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class AdminBookingUserPayload(BaseModel):
    user_id: int
    telegram_user_id: int
    telegram_username: Optional[str] = None
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None


class AdminBookingItemPayload(BaseModel):
    booking_id: int
    status: str
    topic: Optional[str] = None
    is_urgent: bool = False
    meeting_format: Optional[str] = None
    duration_minutes: Optional[int] = None
    waitlist_date: Optional[date] = None
    slot_start_at: Optional[datetime] = None
    slot_end_at: Optional[datetime] = None
    requested_new_slot_start_at: Optional[datetime] = None
    requested_new_slot_end_at: Optional[datetime] = None
    comment: Optional[str] = None
    admin_public_comment: Optional[str] = None
    meeting_link: Optional[str] = None
    calendar_event_id: Optional[str] = None
    updated_at: datetime
    user: AdminBookingUserPayload


class AdminBookingsListResponse(BaseModel):
    items: List[AdminBookingItemPayload]


class AdminDecisionRequest(BaseModel):
    init_data: str = Field(min_length=1)
    admin_public_comment: Optional[str] = None
    meeting_link: Optional[str] = None


class AdminUpdateBookingMetaRequest(BaseModel):
    init_data: str = Field(min_length=1)
    admin_public_comment: Optional[str] = None
    meeting_link: Optional[str] = None


class AdminOfferWaitlistSlotRequest(BaseModel):
    init_data: str = Field(min_length=1)
    slot_key: str = Field(min_length=1)


class AdminBookingActionResponse(BaseModel):
    booking_id: int
    status: str
    message: str
    admin_public_comment: Optional[str] = None
    meeting_link: Optional[str] = None
