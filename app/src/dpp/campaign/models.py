import enum
import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Computed,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from dpp.db import Base

EMBEDDING_DIM = 1536  # text-embedding-3-small


class District(Base):
    """A node in the arbitrary-depth party unit hierarchy (see spec canv-01).

    Example instance: LV Berlin -> BV Friedrichshain-Kreuzberg -> OV Kreuzberg.
    The hierarchy depth is not fixed; any node may have any number of children.
    """

    __tablename__ = "districts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("districts.id", ondelete="CASCADE"), nullable=True
    )

    parent: Mapped["District | None"] = relationship(
        "District", remote_side="District.id", back_populates="children"
    )
    children: Mapped[list["District"]] = relationship(
        "District", back_populates="parent", cascade="all, delete-orphan"
    )
    campaigns: Mapped[list["Campaign"]] = relationship(back_populates="district")
    initiatives: Mapped[list["Initiative"]] = relationship(back_populates="district")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<District {self.name!r}>"


class CampaignStatus(str, enum.Enum):
    """Campaign lifecycle statuses. See spec canv-05."""

    DRAFT = "draft"
    REVIEW = "review"
    RUNNING = "running"
    FINISHED = "finished"
    ABORTED = "aborted"
    ARCHIVED = "archived"

    @property
    def label(self) -> str:
        return {
            CampaignStatus.DRAFT: "Entwurf",
            CampaignStatus.REVIEW: "Überprüfung",
            CampaignStatus.RUNNING: "Laufend",
            CampaignStatus.FINISHED: "Abgeschlossen",
            CampaignStatus.ABORTED: "Abgebrochen",
            CampaignStatus.ARCHIVED: "Archiviert",
        }[self]


# Valid forward transitions, per canv-05. Review can also send back to Draft.
ALLOWED_TRANSITIONS: dict[CampaignStatus, set[CampaignStatus]] = {
    CampaignStatus.DRAFT: {CampaignStatus.REVIEW},
    CampaignStatus.REVIEW: {CampaignStatus.DRAFT, CampaignStatus.RUNNING},
    CampaignStatus.RUNNING: {CampaignStatus.FINISHED, CampaignStatus.ABORTED},
    CampaignStatus.FINISHED: {CampaignStatus.ARCHIVED},
    CampaignStatus.ABORTED: {CampaignStatus.ARCHIVED},
    CampaignStatus.ARCHIVED: set(),
}

CLOSED_STATUSES = {CampaignStatus.FINISHED, CampaignStatus.ABORTED, CampaignStatus.ARCHIVED}


class Campaign(Base):
    """A campaign canvas instance. See spec canv-01/canv-02/canv-05."""

    __tablename__ = "campaigns"
    __table_args__ = (Index("ix_campaigns_search_vector", "search_vector", postgresql_using="gin"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    district_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("districts.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[CampaignStatus] = mapped_column(
        Enum(CampaignStatus, name="campaign_status", native_enum=False, length=20),
        nullable=False,
        default=CampaignStatus.DRAFT,
    )
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Zieldefinition
    thema: Mapped[str | None] = mapped_column(Text, nullable=True)
    ziel: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Zielgruppen & Kanäle
    zielgruppen: Mapped[str | None] = mapped_column(Text, nullable=True)
    kanaele: Mapped[str | None] = mapped_column(Text, nullable=True)
    momentum: Mapped[str | None] = mapped_column(Text, nullable=True)
    motiv: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Material, Organisation & Storytelling
    service: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_harvest: Mapped[str | None] = mapped_column(Text, nullable=True)
    tools: Mapped[str | None] = mapped_column(Text, nullable=True)
    phasen_flow: Mapped[str | None] = mapped_column(Text, nullable=True)
    storytelling: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Separate embeddings distinguish political domain from campaign narrative.
    # See adr-04 for the privacy exception this implies.
    domain_embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    narrative_embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_summary_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('german'::regconfig, "
            "coalesce(thema, '') || ' ' || coalesce(ziel, '') || ' ' || "
            "coalesce(zielgruppen, '') || ' ' || coalesce(kanaele, '') || ' ' || "
            "coalesce(momentum, '') || ' ' || coalesce(motiv, '') || ' ' || "
            "coalesce(service, '') || ' ' || coalesce(data_harvest, '') || ' ' || "
            "coalesce(tools, '') || ' ' || coalesce(phasen_flow, '') || ' ' || "
            "coalesce(storytelling, '') || ' ' || coalesce(ai_summary, ''))",
            persisted=True,
        ),
        nullable=False,
        deferred=True,
    )

    forked_from_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    district: Mapped["District"] = relationship(back_populates="campaigns")
    forked_from: Mapped["Campaign | None"] = relationship(remote_side="Campaign.id")
    initiative_links: Mapped[list["InitiativeCampaign"]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan"
    )
    retrospective: Mapped["Retrospective | None"] = relationship(
        back_populates="campaign", cascade="all, delete-orphan", uselist=False
    )

    GOAL_FIELDS = ("thema", "ziel")
    AUDIENCE_FIELDS = ("zielgruppen", "kanaele", "momentum", "motiv")
    EXECUTION_FIELDS = ("service", "data_harvest", "tools", "phasen_flow", "storytelling")

    @property
    def goal_complete(self) -> bool:
        return all(getattr(self, field) for field in self.GOAL_FIELDS)

    @property
    def audience_complete(self) -> bool:
        return all(getattr(self, field) for field in self.AUDIENCE_FIELDS)

    @property
    def audience_unlocked(self) -> bool:
        return self.goal_complete

    @property
    def execution_unlocked(self) -> bool:
        return self.goal_complete and self.audience_complete

    @property
    def execution_complete(self) -> bool:
        return all(getattr(self, field) for field in self.EXECUTION_FIELDS)

    @property
    def canvas_complete(self) -> bool:
        return self.goal_complete and self.audience_complete and self.execution_complete

    @property
    def is_closed(self) -> bool:
        return self.status in CLOSED_STATUSES

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Campaign {self.thema!r} ({self.status})>"


class Initiative(Base):
    """Coordinates campaigns from an anchor district and its descendants,
    and tracks domain and narrative similarity scores across them. See spec canv-01.

    The anchor district is fixed after creation; cross-branch membership is
    outside v1 scope.
    """

    __tablename__ = "initiatives"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    district_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("districts.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    domain_similarity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    narrative_similarity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    coherence_computed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    district: Mapped["District"] = relationship(back_populates="initiatives")
    campaign_links: Mapped[list["InitiativeCampaign"]] = relationship(
        back_populates="initiative", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Initiative {self.name!r}>"


class InitiativeCampaign(Base):
    """Association between an Initiative and its member Campaigns."""

    __tablename__ = "initiative_campaigns"
    __table_args__ = (UniqueConstraint("initiative_id", "campaign_id", name="uq_initiative_campaign"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    initiative_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("initiatives.id", ondelete="CASCADE"), nullable=False
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )

    initiative: Mapped["Initiative"] = relationship(back_populates="campaign_links")
    campaign: Mapped["Campaign"] = relationship(back_populates="initiative_links")


class Retrospective(Base):
    """Post-mortem / knowledge retention record for a closed campaign.

    See spec canv-04. Auto-created (empty) when a campaign transitions to
    Finished or Aborted (see canv-05).
    """

    __tablename__ = "retrospectives"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), unique=True, nullable=False
    )

    zielerreichung: Mapped[str | None] = mapped_column(Text, nullable=True)
    was_lief_gut: Mapped[str | None] = mapped_column(Text, nullable=True)
    was_lief_schlecht: Mapped[str | None] = mapped_column(Text, nullable=True)
    handlungsempfehlungen: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    campaign: Mapped["Campaign"] = relationship(back_populates="retrospective")
