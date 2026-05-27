"""users table for JWT auth + RBAC

Adds the `users` table that backs the JWT login flow (audit finding C1).

Columns:
  - id            UUID primary key
  - email         TEXT with a unique constraint (auth layer lower()s before
                  comparing — avoids the CITEXT extension)
  - password_hash bcrypt hash via passlib (`$2b$...` ~60 chars)
  - name          display name shown in UI
  - role          enum (admin / editor / viewer) — RBAC enforcement
  - is_active     soft-disable without delete (preserves audit trail)
  - created_at / updated_at  standard audit timestamps
  - token_version monotonically-incrementing counter; refresh tokens
                  carry this value as a claim and the auth layer
                  rejects any token whose version is below the current
                  one. Bump it to revoke all sessions for a user
                  (password change, compromise, etc.)

Revision ID: 20260527_0010
Revises: 20260527_0009
Create Date: 2026-05-27 13:32:58.391045
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260527_0010"
down_revision: str | None = "20260527_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column(
            "role",
            sa.Enum("admin", "editor", "viewer", name="user_role"),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_is_active", "users", ["is_active"], unique=False)
    op.create_index("ix_users_role", "users", ["role"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_users_role", table_name="users")
    op.drop_index("ix_users_is_active", table_name="users")
    op.drop_table("users")
    sa.Enum(name="user_role").drop(op.get_bind(), checkfirst=True)
