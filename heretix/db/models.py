from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Float,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for ORM models."""


UUID_TYPE = PG_UUID(as_uuid=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    plan: Mapped[str] = mapped_column(String(32), nullable=False, default="trial")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    sessions: Mapped[List[Session]] = relationship(back_populates="user", cascade="all, delete-orphan")
    email_tokens: Mapped[List[EmailToken]] = relationship(back_populates="user", cascade="all, delete-orphan")
    checks: Mapped[List[Check]] = relationship(back_populates="user")
    usage_periods: Mapped[List[UsageLedger]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Session(Base):  # noqa: D401 - simple data container
    """Active authenticated session."""

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    user_agent: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)

    user: Mapped[User] = relationship(back_populates="sessions")

    __table_args__ = (Index("ix_sessions_user_id", "user_id"),)


class EmailToken(Base):
    __tablename__ = "email_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    selector: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    verifier_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="email_tokens")

    __table_args__ = (Index("ix_email_tokens_user_id", "user_id"),)


class Check(Base):  # noqa: D401 - simple data container
    """Single Raw Prior Lens run."""

    __tablename__ = "checks"

    id: Mapped[uuid.UUID] = mapped_column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    env: Mapped[str] = mapped_column(String(16), nullable=False)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID_TYPE, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    claim: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    claim_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    k: Mapped[int] = mapped_column("K", Integer, nullable=False)
    r: Mapped[int] = mapped_column("R", Integer, nullable=False)
    t: Mapped[Optional[int]] = mapped_column("T", Integer, nullable=True)
    b: Mapped[Optional[int]] = mapped_column("B", Integer, nullable=True)
    seed: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    bootstrap_seed: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_output_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    prob_true_rpl: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ci_lo: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ci_hi: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ci_width: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    template_iqr_logit: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    stability_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    imbalance_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rpl_compliance_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cache_hit_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    config_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sampler_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    counts_by_template_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    artifact_json_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    prompt_char_len_max: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pqs: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    gate_compliance_ok: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    gate_stability_ok: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    gate_precision_ok: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    pqs_version: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    was_cached: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    provider_model_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[Optional[User]] = relationship(back_populates="checks")

    __table_args__ = (
        Index("ix_checks_user_id", "user_id"),
        Index("ix_checks_env", "env"),
        Index("ix_checks_claim_hash", "claim_hash"),
    )


class UsageLedger(Base):
    __tablename__ = "usage_ledger"

    id: Mapped[uuid.UUID] = mapped_column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID_TYPE, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    plan: Mapped[str] = mapped_column(String(32), nullable=False)
    checks_allowed: Mapped[int] = mapped_column(Integer, nullable=False)
    checks_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="usage_periods")

    __table_args__ = (
        UniqueConstraint("user_id", "period_start", name="uq_usage_period"),
        Index("ix_usage_user", "user_id"),
    )


class ResultCache(Base):
    __tablename__ = "result_cache"

    id: Mapped[uuid.UUID] = mapped_column(UUID_TYPE, primary_key=True, default=uuid.uuid4)
    result_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    env: Mapped[str] = mapped_column(String(16), nullable=False)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID_TYPE, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    payload: Mapped[dict] = mapped_column(JSON_TYPE, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped[Optional[User]] = relationship()

    __table_args__ = (
        Index("ix_result_cache_env", "env"),
        Index("ix_result_cache_user", "user_id"),
    )
