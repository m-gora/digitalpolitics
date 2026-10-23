import enum
import secrets
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from geoalchemy2 import Geography
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from dpp.db import Base

if TYPE_CHECKING:
    from dpp.campaign.models import Campaign


class QuestionnaireStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    CLOSED = "closed"


class Questionnaire(Base):
    __tablename__ = "questionnaires"
    __table_args__ = (
        CheckConstraint("char_length(title) BETWEEN 1 AND 100", name="ck_questionnaire_title_length"),
        Index("ix_questionnaires_campaign_id", "campaign_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, default=lambda: secrets.token_urlsafe(24))
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    intro: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[QuestionnaireStatus] = mapped_column(
        Enum(QuestionnaireStatus, name="questionnaire_status", native_enum=False, length=10),
        nullable=False,
        default=QuestionnaireStatus.DRAFT,
    )
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True
    )
    collection_stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    collection_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    questions: Mapped[list["Question"]] = relationship(
        back_populates="questionnaire", cascade="all, delete-orphan", order_by="Question.position"
    )
    campaign: Mapped["Campaign | None"] = relationship()
    responses: Mapped[list["Response"]] = relationship(back_populates="questionnaire", cascade="all, delete-orphan")


class Question(Base):
    __tablename__ = "crowd_questions"
    __table_args__ = (
        CheckConstraint("position BETWEEN 1 AND 5", name="ck_crowd_question_position"),
        CheckConstraint("char_length(prompt) BETWEEN 1 AND 200", name="ck_crowd_question_prompt_length"),
        CheckConstraint("question_type IN ('text', 'single_choice', 'multiple_choice')", name="ck_crowd_question_type"),
        UniqueConstraint("questionnaire_id", "position", name="uq_crowd_question_position"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    questionnaire_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("questionnaires.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt: Mapped[str] = mapped_column(String(200), nullable=False)
    question_type: Mapped[str] = mapped_column(String(20), nullable=False)
    required: Mapped[bool] = mapped_column(nullable=False, default=True)
    # Stable UUID values allow submitted choices to be checked against a frozen definition.
    options: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    questionnaire: Mapped[Questionnaire] = relationship(back_populates="questions")


class Response(Base):
    __tablename__ = "crowd_responses"
    __table_args__ = (
        UniqueConstraint("questionnaire_id", "client_id", name="uq_crowd_response_client"),
        Index("ix_crowd_responses_location", "location", postgresql_using="gist"),
        Index("ix_crowd_responses_received_at", "received_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    questionnaire_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("questionnaires.id", ondelete="CASCADE"), nullable=False
    )
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    location: Mapped[object] = mapped_column(Geography(geometry_type="POINT", srid=4326), nullable=False)
    accuracy_m: Mapped[float] = mapped_column(nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    # Only scrubbed answers; keys are stable question UUIDs. Values have text/options/via_voice.
    answers: Mapped[dict] = mapped_column(JSONB, nullable=False)

    questionnaire: Mapped[Questionnaire] = relationship(back_populates="responses")
