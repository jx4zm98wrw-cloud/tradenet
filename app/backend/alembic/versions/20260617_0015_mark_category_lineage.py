"""Derived mark_category + lineage_key (STORED generated columns).

Classification was assigned imperatively by the extractor and had drifted from
the gazette's identifying signs — 2,605 Madrid registrations (field 111 with no
210) were mislabeled `B_domestic`. Rather than re-tag rows (a cache that goes
stale), the classification and the lifecycle identity become pure functions of
the identifying signs, materialized as STORED generated columns so they can
never drift and need no backfill as the corpus grows.

mark_category — one row's stage, from (210/111/116) presence:
  - domestic_application   : 210 only                     (Gazette A)
  - domestic_registration  : 210 + 111                    (Gazette B §1)
  - madrid_registration    : 111 only (no 210/116)        (Gazette B §2 — IRN in 111)
  - madrid_renewal         : 116 only (no 210/111)        (Gazette B §3 — IRN in 116)
  - unknown                : anything else (surfaces malformed rows)

lineage_key — the identity that links a mark's rows across gazette years:
  COALESCE(210, 111, 116). Domestic A↔B§1 share the 210 (B§1 has 210+111, so
  COALESCE picks 210). Madrid §2↔§3 share the WIPO International Registration
  Number, stored in 111 at acceptance (§2) and 116 at renewal (§3) — same value,
  so COALESCE yields the IRN for both. Domestic (4-…) and Madrid (bare 7-digit
  IRN) number spaces don't collide.

Both excluded from `alembic check` drift detection in env.py (the stored
CASE/COALESCE is normalised by Postgres and would otherwise be flagged against
the model's Computed() string).

Revision ID: 20260617_0015
Revises: 20260616_0014
Create Date: 2026-06-17

"""

from __future__ import annotations

from alembic import op

revision: str = "20260617_0015"
down_revision: str | None = "20260616_0014"
branch_labels = None
depends_on = None

_MARK_CATEGORY_EXPR = """
CASE
  WHEN nullif(application_number,'') IS NOT NULL
       AND nullif(certificate_number,'') IS NULL
       AND nullif(madrid_number,'') IS NULL          THEN 'domestic_application'
  WHEN nullif(application_number,'') IS NOT NULL
       AND nullif(certificate_number,'') IS NOT NULL THEN 'domestic_registration'
  WHEN nullif(certificate_number,'') IS NOT NULL
       AND nullif(application_number,'') IS NULL
       AND nullif(madrid_number,'') IS NULL          THEN 'madrid_registration'
  WHEN nullif(madrid_number,'') IS NOT NULL
       AND nullif(certificate_number,'') IS NULL
       AND nullif(application_number,'') IS NULL      THEN 'madrid_renewal'
  ELSE 'unknown'
END
"""

_LINEAGE_KEY_EXPR = (
    "COALESCE(nullif(application_number,''), nullif(certificate_number,''), "
    "nullif(madrid_number,''))"
)


def upgrade() -> None:
    op.execute(
        f"ALTER TABLE trademarks ADD COLUMN mark_category text "
        f"GENERATED ALWAYS AS ({_MARK_CATEGORY_EXPR}) STORED"
    )
    op.execute(
        f"ALTER TABLE trademarks ADD COLUMN lineage_key text "
        f"GENERATED ALWAYS AS ({_LINEAGE_KEY_EXPR}) STORED"
    )
    op.execute("CREATE INDEX ix_trademarks_mark_category ON trademarks (mark_category)")
    op.execute("CREATE INDEX ix_trademarks_lineage_key ON trademarks (lineage_key)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_trademarks_lineage_key")
    op.execute("DROP INDEX IF EXISTS ix_trademarks_mark_category")
    op.execute("ALTER TABLE trademarks DROP COLUMN IF EXISTS lineage_key")
    op.execute("ALTER TABLE trademarks DROP COLUMN IF EXISTS mark_category")
