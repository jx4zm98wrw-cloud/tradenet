"""Search recall indexes: lower(mark_sample) trigram + representative pub-date sort.

Fixes two hot-path seq scans found in the 2026-07-02 audit (P1a, P1c):

* **P1a** — the phonetic recall filters `lower(mark_sample) % :q`, but the only
  `ix_trademarks_mark_sample_trgm` in the DB is on the RAW column (a name
  collision: the model defines it on `mark_sample`, and migration 0012's
  `lower(mark_sample)` version was silently skipped by `CREATE INDEX IF NOT
  EXISTS`). So that arm seq-scanned the whole table. Create the missing
  `lower(mark_sample)` GIN-trgm index under a NON-colliding name. (`mark_name`
  already has its `lower()` index from 0032.)

* **P1c** — the default Search sort (`ORDER BY publication_date_441 DESC NULLS
  LAST, id` over `is_representative` rows) had no supporting index → a full sort
  of ~89k rows on every unfiltered load. Add a partial composite matching that
  ordering.

Both are functional/partial indexes not expressible on the model, so their names
are added to `_MANUAL_INDEXES` in alembic/env.py (else `alembic check` reports
phantom drop-index drift).
"""

from __future__ import annotations

from alembic import op

revision: str = "20260702_0035"
down_revision: str | None = "20260701_0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_trademarks_mark_sample_ltrgm "
        "ON trademarks USING gin (lower(mark_sample) gin_trgm_ops) "
        "WHERE mark_sample IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_trademarks_pubdate_rep "
        "ON trademarks (publication_date_441 DESC NULLS LAST, id) "
        "WHERE is_representative"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_trademarks_pubdate_rep")
    op.execute("DROP INDEX IF EXISTS ix_trademarks_mark_sample_ltrgm")
