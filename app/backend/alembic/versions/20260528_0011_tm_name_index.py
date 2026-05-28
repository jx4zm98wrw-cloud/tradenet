"""Add tm_name_index reference table for wordmark enrichment.

The existing extraction pipeline (`tm_extractor.processor`) reliably pulls
INID `(540)` wordmarks only on a small fraction of gazette rows — at the time
this migration lands, 100% of `record_type='A'` rows and 95.5% of
`record_type='B_domestic'` rows have NULL/empty `mark_sample`. The figurative
elements + logos extract cleanly; the wordmark text doesn't.

NOIP separately publishes an applicant-name extract covering 2008→present
which has clean `(210)` → `(540)` mappings. We load it into this reference
table once, then run a one-shot `UPDATE trademarks ... FROM tm_name_index`
to fill the missing `mark_sample` values (see
`scripts/enrich_mark_samples.py`).

The reference table stays around after enrichment for two reasons:
  1. Future PDF ingests can re-run the enrichment script to pick up
     wordmarks for newly-added rows whose app numbers are already in this
     index.
  2. If NOIP publishes a refreshed/expanded name extract, we can
     `TRUNCATE tm_name_index` + reload + re-enrich without changing any
     other state.

Schema is intentionally minimal — 3 columns, primary key on app number,
trigram index on mark_sample. No FK to `gazettes` (the CSV has no per-PDF
provenance; many rows are for applications never matched to a gazette we've
ingested). No `record_type` column because every row in this index is by
definition an A-file application — the CSV publishes only filings.

Revision ID: 20260528_0011
Revises: 20260527_0010
Create Date: 2026-05-28 17:30:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260528_0011"
down_revision: str | None = "20260527_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE tm_name_index (
            application_number  VARCHAR(64) PRIMARY KEY,
            submission_date     DATE,
            mark_sample         TEXT NOT NULL
        )
        """
    )

    # Trigram GIN to make this table useful for fuzzy search of the full
    # 770k-row mark corpus down the road. Cheap to create up front; if we
    # only ever use the table for app-number-keyed enrichment, the index
    # is still ~harmless (gets touched on inserts but the loader does
    # one bulk COPY, not row-by-row).
    op.execute(
        "CREATE INDEX ix_tm_name_index_mark_trgm "
        "ON tm_name_index USING gin (mark_sample gin_trgm_ops)"
    )

    # Optional but cheap: lets us answer "what was filed in 2018?" without
    # a seq scan. Will only see use if a future feature exposes the
    # historical index in the UI.
    op.execute(
        "CREATE INDEX ix_tm_name_index_submission_date "
        "ON tm_name_index (submission_date)"
    )


def downgrade() -> None:
    # CASCADE because the trigram + date indexes hang off the table —
    # listing them explicitly would be defensive theater since they're
    # 1:1 with this table's lifetime.
    op.execute("DROP TABLE IF EXISTS tm_name_index CASCADE")
