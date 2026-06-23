"""domestic_not_found negative-cache table + not_found counter on the sweep control

A IP VIETNAM detail fetch can return HTTP 200 with a ~2,178-byte skeleton page that
carries no `product-form-label` marker — a definitive "not published yet", not
flakiness (stable across 40+ attempts). This table records each such mark so the
sweep can skip it for a backoff window (it re-checks after the window as IP VIETNAM
publishes the detail), instead of retrying it to exhaustion every chunk and
tripping the circuit breaker on the stably-ordered front of the work-list.

Revision ID: 20260623_0024
Revises: 20260622_0023
Create Date: 2026-06-23
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "20260623_0024"
down_revision: str | None = "20260622_0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "domestic_not_found",
        sa.Column("application_number", sa.Text(), primary_key=True),
        sa.Column("vnid", sa.Text()),
        sa.Column(
            "first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "last_checked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("check_count", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )
    # The sweep's backoff filter selects on last_checked_at; index it.
    op.create_index(
        "ix_domestic_not_found_last_checked_at", "domestic_not_found", ["last_checked_at"]
    )
    # Per-run not_found counter on the control singleton (distinct from `failed`):
    # a not_found is a recorded definitive negative, not a fetch failure.
    op.add_column(
        "domestic_sweep_control",
        sa.Column("not_found", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("domestic_sweep_control", "not_found")
    op.drop_index("ix_domestic_not_found_last_checked_at", table_name="domestic_not_found")
    op.drop_table("domestic_not_found")
