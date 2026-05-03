from __future__ import annotations

import logging
from typing import Awaitable, Callable

from app.modules.jobs.service import JobsRunResult, JobsService

logger = logging.getLogger(__name__)

UserNotifier = Callable[[int, str], Awaitable[None]]


async def run_jobs_once_with_notifications(
    jobs_service: JobsService,
    notify_user: UserNotifier,
) -> JobsRunResult:
    result = jobs_service.run_once()
    delivered = 0
    for notice in result.notices:
        try:
            await notify_user(notice.user_telegram_user_id, notice.text)
            delivered += 1
        except Exception:
            logger.exception(
                "Failed to deliver TTL notification: booking_id=%s telegram_user_id=%s",
                notice.booking_id,
                notice.user_telegram_user_id,
            )
    logger.info(
        "Background notifications done: delivered=%s planned=%s",
        delivered,
        len(result.notices),
    )
    return result
