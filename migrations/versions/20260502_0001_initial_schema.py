"""Initial schema for stage 1 foundation.

Revision ID: 20260502_0001
Revises:
Create Date: 2026-05-02
"""

from alembic import op
import sqlalchemy as sa


revision = "20260502_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_username", sa.String(length=255), nullable=True),
        sa.Column("telegram_display_name", sa.String(length=255), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("is_blocked", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_users_telegram_user_id", "users", ["telegram_user_id"], unique=True)

    op.create_table(
        "bookings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("topic", sa.String(length=255), nullable=True),
        sa.Column("format", sa.String(length=32), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column("slot_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("slot_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("requested_new_slot_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("requested_new_slot_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("previous_slot_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("previous_slot_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("calendar_event_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_bookings_user_id", "bookings", ["user_id"], unique=False)

    op.create_table(
        "status_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("booking_id", sa.Integer(), sa.ForeignKey("bookings.id"), nullable=False),
        sa.Column("old_status", sa.String(length=64), nullable=True),
        sa.Column("new_status", sa.String(length=64), nullable=False),
        sa.Column("changed_by", sa.String(length=32), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_status_history_booking_id", "status_history", ["booking_id"], unique=False)

    op.create_table(
        "availability_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "closed_dates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_closed_dates_date", "closed_dates", ["date"], unique=True)

    op.create_table(
        "time_blocks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("comment", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_time_blocks_date", "time_blocks", ["date"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_time_blocks_date", table_name="time_blocks")
    op.drop_table("time_blocks")

    op.drop_index("ix_closed_dates_date", table_name="closed_dates")
    op.drop_table("closed_dates")

    op.drop_table("availability_rules")

    op.drop_index("ix_status_history_booking_id", table_name="status_history")
    op.drop_table("status_history")

    op.drop_index("ix_bookings_user_id", table_name="bookings")
    op.drop_table("bookings")

    op.drop_index("ix_users_telegram_user_id", table_name="users")
    op.drop_table("users")
