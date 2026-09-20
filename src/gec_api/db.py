"""SQLAlchemy models. Portable (SQLite for the local demo, PostgreSQL via GEC_DATABASE_URL)."""
from __future__ import annotations

import datetime as dt
import os

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from gec_common.config import gec_home


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(16))  # learner | educator | admin
    display_name: Mapped[str] = mapped_column(String(128), default="")
    # Only independent educators feed the 'educator acceptance' metric. Demo/self-review accounts are False.
    is_independent_educator: Mapped[bool] = mapped_column(Boolean, default=False)
    preferred_language: Mapped[str] = mapped_column(String(8), default="en", server_default="en")


class Submission(Base):
    __tablename__ = "submissions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    language: Mapped[str] = mapped_column(String(8), index=True)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    runs: Mapped[list["CorrectionRun"]] = relationship(back_populates="submission")


class CorrectionRun(Base):
    __tablename__ = "correction_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey("submissions.id"), index=True)
    pipeline: Mapped[str] = mapped_column(String(8))
    mode: Mapped[str] = mapped_column(String(16))
    corrected: Mapped[str] = mapped_column(Text)
    degraded: Mapped[bool] = mapped_column(Boolean, default=False)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)  # model_ids, warnings, trace, flags, capability, lang detection
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    submission: Mapped[Submission] = relationship(back_populates="runs")
    edits: Mapped[list["EditRow"]] = relationship(back_populates="run", order_by="EditRow.start")


class EditRow(Base):
    __tablename__ = "edits"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("correction_runs.id"), index=True)
    start: Mapped[int] = mapped_column(Integer)
    end: Mapped[int] = mapped_column(Integer)
    original: Mapped[str] = mapped_column(Text)
    replacement: Mapped[str] = mapped_column(Text)
    op: Mapped[str] = mapped_column(String(8))
    language: Mapped[str] = mapped_column(String(8))
    error_type: Mapped[str] = mapped_column(String(48))
    rule_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source: Mapped[str] = mapped_column(String(96))
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence_calibrated: Mapped[bool] = mapped_column(Boolean, default=False)
    gate_status: Mapped[str] = mapped_column(String(16), default="not_applicable")
    gate_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    scores: Mapped[dict] = mapped_column(JSON, default=dict)
    explanation: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    learner_decision: Mapped[str | None] = mapped_column(String(16), nullable=True)
    run: Mapped[CorrectionRun] = relationship(back_populates="edits")
    adjudications: Mapped[list["Adjudication"]] = relationship(back_populates="edit")


class Adjudication(Base):
    """Append-only educator verdicts."""
    __tablename__ = "adjudications"
    id: Mapped[int] = mapped_column(primary_key=True)
    edit_id: Mapped[int] = mapped_column(ForeignKey("edits.id"), index=True)
    educator_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    verdict: Mapped[str] = mapped_column(String(16))  # accept | reject | revise
    revised_replacement: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_type_override: Mapped[str | None] = mapped_column(String(48), nullable=True)
    meaning_changed: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, default="")
    reviewer_independent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    edit: Mapped[EditRow] = relationship(back_populates="adjudications")


class LearnerProgress(Base):
    """Materialised snapshot of a learner's error profile (rebuildable from edits + adjudications)."""
    __tablename__ = "learner_progress"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    language: Mapped[str] = mapped_column(String(8))
    error_type: Mapped[str] = mapped_column(String(48))
    total: Mapped[int] = mapped_column(Integer, default=0)
    recent_per_100_tokens: Mapped[float] = mapped_column(Float, default=0.0)
    trend: Mapped[str] = mapped_column(String(24), default="insufficient_data")
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    pipeline: Mapped[str] = mapped_column(String(8))
    mode: Mapped[str] = mapped_column(String(16))
    dataset: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="running")  # running | done | failed
    progress: Mapped[str] = mapped_column(String(32), default="")
    report: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


def database_url() -> str:
    return os.environ.get("GEC_DATABASE_URL") or f"sqlite:///{(gec_home() / 'gec_demo.db').as_posix()}"


_engine = None
SessionLocal = None


def init_db(url: str | None = None):
    global _engine, SessionLocal
    url = url or database_url()
    kw = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {}
    _engine = create_engine(url, **kw)
    SessionLocal = sessionmaker(_engine, expire_on_commit=False)
    Base.metadata.create_all(_engine)
    _ensure_columns(_engine)
    return _engine


def _ensure_columns(engine) -> None:
    """Add columns introduced after a database was first created (create_all never alters existing tables)."""
    from sqlalchemy import inspect, text

    cols = {c["name"] for c in inspect(engine).get_columns("users")}
    if "preferred_language" not in cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN preferred_language VARCHAR(8) NOT NULL DEFAULT 'en'"))


class RevokedToken(Base):
    """Signed-out JWTs (server-side revocation so a stolen token cannot outlive sign-out)."""
    __tablename__ = "revoked_tokens"
    jti: Mapped[str] = mapped_column(String(64), primary_key=True)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
