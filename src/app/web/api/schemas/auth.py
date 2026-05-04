from __future__ import annotations

from typing import Literal
from typing import Optional

from pydantic import BaseModel, Field


ModeName = Literal["client", "admin"]


class AuthSessionRequest(BaseModel):
    init_data: str = Field(min_length=1)


class AuthModeSwitchRequest(BaseModel):
    init_data: str = Field(min_length=1)
    mode: ModeName


class AuthUserPayload(BaseModel):
    telegram_user_id: int
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    username: Optional[str] = None


class AuthAccessPayload(BaseModel):
    is_admin: bool
    available_modes: list[ModeName]
    default_mode: ModeName
    current_mode: ModeName


class AuthSessionResponse(BaseModel):
    user: AuthUserPayload
    access: AuthAccessPayload
