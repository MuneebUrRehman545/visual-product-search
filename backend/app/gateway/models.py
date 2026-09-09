import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import DateTime, Float, ForeignKey, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

try:
    from backend.app.gateway.database import Base
except ImportError:
    from app.gateway.database import Base


def generate_uuid_str() -> str:
    return str(uuid.uuid4())


def get_utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PipelineRun(Base):
    """
    Top-level pipeline execution trace spanning Gateway -> Vision -> RAG -> Agent.
    Corresponds to the shared `pipeline_runs` table in PostgreSQL.
    """
    __tablename__ = "pipeline_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid_str)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="created")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), default=get_utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=get_utc_now,
        onupdate=func.now(),
    )

    # Relationships
    events: Mapped[List["ModuleEvent"]] = relationship(
        back_populates="pipeline_run",
        cascade="all, delete-orphan",
        order_by="ModuleEvent.created_at",
    )
    extracted_data_records: Mapped[List["ExtractedData"]] = relationship(
        back_populates="pipeline_run",
        cascade="all, delete-orphan",
    )
    rag_documents: Mapped[List["RagDocument"]] = relationship(
        back_populates="pipeline_run",
        cascade="all, delete-orphan",
    )
    assets: Mapped[List["Asset"]] = relationship(
        back_populates="pipeline_run",
        cascade="all, delete-orphan",
    )
    chat_messages: Mapped[List["ChatHistory"]] = relationship(
        back_populates="pipeline_run",
        cascade="all, delete-orphan",
    )
    agent_runs: Mapped[List["AgentRun"]] = relationship(
        back_populates="pipeline_run",
        cascade="all, delete-orphan",
    )


class ModuleEvent(Base):
    """
    Shared multi-module lifecycle audit log and telemetry.
    Corresponds to the shared `module_events` table in PostgreSQL.
    """
    __tablename__ = "module_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid_str)
    pipeline_run_id: Mapped[str] = mapped_column(String(36), ForeignKey("pipeline_runs.id", ondelete="CASCADE"), nullable=False)
    module: Mapped[str] = mapped_column(String(64), nullable=False)  # 'gateway', 'vision', 'rag', 'agent'
    event: Mapped[str] = mapped_column(String(64), nullable=False)   # 'created', 'started', 'completed', 'failed'
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    payload: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), default=get_utc_now)

    pipeline_run: Mapped["PipelineRun"] = relationship(back_populates="events")


class Asset(Base):
    """
    Multimodal query inputs (e.g. uploaded images).
    Corresponds to shared `assets` table in PostgreSQL.
    """
    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid_str)
    pipeline_run_id: Mapped[str] = mapped_column(String(36), ForeignKey("pipeline_runs.id", ondelete="CASCADE"), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(64), nullable=False, default="query_image")
    filename: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    mime_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    storage_uri: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), default=get_utc_now)

    pipeline_run: Mapped["PipelineRun"] = relationship(back_populates="assets")


class ExtractedData(Base):
    """
    Vision structured match output.
    Corresponds to shared `extracted_data` table in PostgreSQL.
    """
    __tablename__ = "extracted_data"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid_str)
    pipeline_run_id: Mapped[str] = mapped_column(String(36), ForeignKey("pipeline_runs.id", ondelete="CASCADE"), nullable=False)
    asset_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    module: Mapped[str] = mapped_column(String(64), nullable=False, default="vision")
    data_type: Mapped[str] = mapped_column(String(64), nullable=False, default="visual_product_search_matches")
    content: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    model: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), default=get_utc_now)

    pipeline_run: Mapped["PipelineRun"] = relationship(back_populates="extracted_data_records")


class RagDocument(Base):
    """
    RAG retrieved context chunks and knowledge.
    Corresponds to shared `rag_documents` table in PostgreSQL.
    """
    __tablename__ = "rag_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid_str)
    pipeline_run_id: Mapped[str] = mapped_column(String(36), ForeignKey("pipeline_runs.id", ondelete="CASCADE"), nullable=False)
    source_extracted_data_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), default=get_utc_now)

    pipeline_run: Mapped["PipelineRun"] = relationship(back_populates="rag_documents")


class ChatHistory(Base):
    """
    Conversational message history per pipeline run.
    Corresponds to shared `chat_history` table in PostgreSQL.
    """
    __tablename__ = "chat_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid_str)
    pipeline_run_id: Mapped[str] = mapped_column(String(36), ForeignKey("pipeline_runs.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), default=get_utc_now)

    pipeline_run: Mapped["PipelineRun"] = relationship(back_populates="chat_messages")


class AgentRun(Base):
    """
    Agent execution summary and decision outcome.
    Corresponds to shared `agent_runs` table in PostgreSQL.
    """
    __tablename__ = "agent_runs"

    agent_run_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid_str)
    pipeline_run_id: Mapped[str] = mapped_column(String(36), ForeignKey("pipeline_runs.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="in_progress")
    decision: Mapped[str] = mapped_column(String(50), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), default=get_utc_now)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    pipeline_run: Mapped["PipelineRun"] = relationship(back_populates="agent_runs")
    actions: Mapped[List["AgentAction"]] = relationship(
        back_populates="agent_run",
        cascade="all, delete-orphan",
    )


class AgentAction(Base):
    """
    Granular action, evaluation step, or tool call trace.
    Corresponds to shared `agent_actions` table in PostgreSQL.
    """
    __tablename__ = "agent_actions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid_str)
    agent_run_id: Mapped[str] = mapped_column(String(36), ForeignKey("agent_runs.agent_run_id", ondelete="CASCADE"), nullable=False)
    action_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), default=get_utc_now)

    agent_run: Mapped["AgentRun"] = relationship(back_populates="actions")


