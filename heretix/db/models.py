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
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for ORM models."""


UUID_TYPE = PG_UUID(as_uuid=True)
JSON_TYPE = JSONB


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
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID_TYPE, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    env: Mapped[str] = mapped_column(String(16), nullable=False)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    claim_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    claim_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    k: Mapped[int] = mapped_column(Integer, nullable=False)
    r: Mapped[int] = mapped_column(Integer, nullable=False)
    t: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    b: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_output_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    prob_true_rpl: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ci_lo: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ci_hi: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    stability_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    imbalance_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cache_hit_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    aggregation: Mapped[Optional[dict]] = mapped_column(JSON_TYPE, nullable=True)
    diagnostics: Mapped[Optional[dict]] = mapped_column(JSON_TYPE, nullable=True)
    was_cached: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    provider_model_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    user: Mapped[Optional[User]] = relationship(back_populates="checks")

    __table_args__ = (
        Index("ix_checks_user_id", "user_id"),
        Index("ix_checks_env", "env"),
        Index("ix_checks_claim_hash", "claim_hash"),
        Index("ix_checks_run_id", "run_id"),
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
