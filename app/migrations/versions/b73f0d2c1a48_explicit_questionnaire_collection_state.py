"""make active questionnaires the explicit collection state

Revision ID: b73f0d2c1a48
Revises: 9f12a8b36c40
Create Date: 2026-10-23
"""
from collections.abc import Sequence

from alembic import op

revision: str = "b73f0d2c1a48"
down_revision: str | Sequence[str] | None = "9f12a8b36c40"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Previously, ACTIVE could coexist with a non-Running linked campaign and
    # silently fail the public collection predicate. Convert that state into
    # an explicit Draft/Closed status before deploying the new invariant.
    op.execute(
        """
        UPDATE questionnaires AS q
        SET status = CASE
                WHEN c.status IN ('FINISHED', 'ABORTED', 'ARCHIVED') THEN 'CLOSED'
                ELSE 'DRAFT'
            END,
            collection_stopped_at = CASE
                WHEN c.status IN ('FINISHED', 'ABORTED', 'ARCHIVED')
                    THEN COALESCE(q.collection_stopped_at, now())
                ELSE NULL
            END,
            collection_started_at = CASE
                WHEN c.status IN ('FINISHED', 'ABORTED', 'ARCHIVED')
                    THEN COALESCE(q.collection_started_at, q.created_at)
                ELSE NULL
            END
        FROM campaigns AS c
        WHERE q.campaign_id = c.id
          AND q.status = 'ACTIVE'
          AND c.status <> 'RUNNING'
        """
    )


def downgrade() -> None:
    # Deliberately retain the corrected explicit lifecycle state on downgrade;
    # restoring ACTIVE/non-Running combinations would recreate the hidden state.
    pass
