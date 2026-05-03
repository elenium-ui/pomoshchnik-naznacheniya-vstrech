from __future__ import annotations

from datetime import datetime

from app.infrastructure.db.models.status_history import StatusHistory


class StatusHistoryRepository:
    def create_entry(
        self,
        session,
        booking_id: int,
        old_status: str | None,
        new_status: str,
        changed_by: str,
    ) -> StatusHistory:
        row = StatusHistory(
            booking_id=booking_id,
            old_status=old_status,
            new_status=new_status,
            changed_by=changed_by,
        )
        session.add(row)
        session.flush()
        return row

    def delete_older_than(self, session, before_dt: datetime) -> int:
        return (
            session.query(StatusHistory)
            .filter(StatusHistory.changed_at < before_dt)
            .delete(synchronize_session=False)
        )
