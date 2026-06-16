"""Double-Metaphone recall index — close the phonetic recall gap.

The pg_trgm `%` recall (migration 0012) catches sound-alikes that share
character trigrams (NEUREX/NEUROFAX share "neu"/"eur"). It MISSES true
sound-alikes whose spellings diverge enough to share no trigram but still
encode to the same phonemes (e.g. "PHWILLIPS" / "FILLIPS"). This adds an
equality recall path on Postgres `dmetaphone()` so those are reachable too.

Stage 1 (recall) only needs to widen the candidate net — it does NOT need to
match the Python engine's jellyfish.metaphone exactly. Postgres' Double
Metaphone (from fuzzystrmatch) is a fine, fully in-DB recall key; the engine
still does the precise rerank. `dmetaphone(lower(...))` is IMMUTABLE, so the
functional btree indexes are valid and back the `= dmetaphone(:q)` lookups.

Revision ID: 20260616_0013
Revises: 20260616_0012
Create Date: 2026-06-16

"""

from __future__ import annotations

from alembic import op

revision: str = "20260616_0013"
down_revision: str | None = "20260616_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS fuzzystrmatch")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_trademarks_mark_sample_dmeta "
        "ON trademarks (dmetaphone(lower(mark_sample)))"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_trademarks_applicant_name_dmeta "
        "ON trademarks (dmetaphone(lower(applicant_name)))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_trademarks_applicant_name_dmeta")
    op.execute("DROP INDEX IF EXISTS ix_trademarks_mark_sample_dmeta")
    # Leave the fuzzystrmatch extension installed.
