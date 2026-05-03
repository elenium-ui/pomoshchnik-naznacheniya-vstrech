from enum import Enum


class BookingStatus(str, Enum):
    DRAFT = "draft"
    PENDING_DECISION = "pending_decision"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    CANCELED_BY_USER = "canceled_by_user"
    EXPIRED = "expired"


class MeetingFormat(str, Enum):
    ONLINE = "онлайн"
    OFFLINE = "офлайн"


DURATION_OPTIONS = (15, 30, 45, 60, 90)
