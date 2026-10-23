"""add anonymous crowdsourcing questionnaires and spatial responses

Revision ID: 9f12a8b36c40
Revises: c7d2e84b5f10
Create Date: 2026-10-22
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geography
from sqlalchemy.dialects import postgresql

revision: str = "9f12a8b36c40"
down_revision: str | Sequence[str] | None = "c7d2e84b5f10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "questionnaires",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("token", sa.String(64), nullable=False, unique=True),
        sa.Column("title", sa.String(100), nullable=False),
        sa.Column("intro", sa.String(500)),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("campaigns.id", ondelete="SET NULL")),
        sa.Column("collection_stopped_at", sa.DateTime(timezone=True)),
        sa.Column("collection_started_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("char_length(title) BETWEEN 1 AND 100", name="ck_questionnaire_title_length"),
    )
    op.create_index("ix_questionnaires_campaign_id", "questionnaires", ["campaign_id"])
    op.create_table(
        "crowd_questions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("questionnaire_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("questionnaires.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("prompt", sa.String(200), nullable=False),
        sa.Column("question_type", sa.String(20), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("options", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.CheckConstraint("position BETWEEN 1 AND 5", name="ck_crowd_question_position"),
        sa.CheckConstraint("char_length(prompt) BETWEEN 1 AND 200", name="ck_crowd_question_prompt_length"),
        sa.CheckConstraint("question_type IN ('text', 'single_choice', 'multiple_choice')", name="ck_crowd_question_type"),
        sa.UniqueConstraint("questionnaire_id", "position", name="uq_crowd_question_position"),
    )
    op.create_table(
        "crowd_responses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("questionnaire_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("questionnaires.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location", Geography(geometry_type="POINT", srid=4326), nullable=False),
        sa.Column("accuracy_m", sa.Float(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("answers", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint("questionnaire_id", "client_id", name="uq_crowd_response_client"),
    )
    op.create_index("ix_crowd_responses_location", "crowd_responses", ["location"], postgresql_using="gist")
    op.create_index("ix_crowd_responses_received_at", "crowd_responses", ["received_at"])


def downgrade() -> None:
    op.drop_index("ix_crowd_responses_received_at", table_name="crowd_responses")
    op.drop_index("ix_crowd_responses_location", table_name="crowd_responses")
    op.drop_table("crowd_responses")
    op.drop_table("crowd_questions")
    op.drop_index("ix_questionnaires_campaign_id", table_name="questionnaires")
    op.drop_table("questionnaires")
