"""
SQLAlchemy models for brief processing
"""
from sqlalchemy import Column, String, Integer, DateTime, Text, ForeignKey, func, JSON
from sqlalchemy.orm import relationship
import uuid

from app.core.database import Base


class Brief(Base):
    """Track Google Doc brief processing requests"""
    __tablename__ = "briefs"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid.uuid4()))
    google_doc_url = Column(String(1000), nullable=False)
    google_doc_id = Column(String(255), nullable=False, index=True)
    document_title = Column(String(500))
    raw_content = Column(Text)
    parsed_structure = Column(JSON)
    workspace_id = Column(String(255), nullable=False, index=True)
    project_id = Column(String(255), nullable=False, index=True)
    project_name = Column(String(500))
    section_id = Column(String(255))
    section_name = Column(String(500))
    status = Column(String(50), nullable=False, default='pending', index=True)
    total_tasks_expected = Column(Integer, default=0)
    total_tasks_created = Column(Integer, default=0)
    total_tasks_failed = Column(Integer, default=0)
    error_message = Column(Text)
    created_by = Column(String(255))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))

    # Relationships
    tasks = relationship("BriefTask", back_populates="brief", cascade="all, delete-orphan")


class BriefTask(Base):
    """Individual tasks created from briefs"""
    __tablename__ = "brief_tasks"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid.uuid4()))
    brief_id = Column(String(255), ForeignKey("briefs.id", ondelete="CASCADE"), nullable=False, index=True)
    asana_task_gid = Column(String(255), index=True)
    asana_task_url = Column(String(1000))
    task_name = Column(String(1000), nullable=False)
    task_description = Column(Text)
    task_order = Column(Integer)
    custom_fields = Column(JSON)
    status = Column(String(50), nullable=False, default='pending', index=True)
    error_message = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    asana_created_at = Column(DateTime(timezone=True))

    # Relationships
    brief = relationship("Brief", back_populates="tasks")


class ProjectConfig(Base):
    """Stored project configurations for brief processing"""
    __tablename__ = "project_configs"

    id = Column(String(255), primary_key=True)
    name = Column(String(500), nullable=False)
    project_gid = Column(String(255), nullable=False)
    section_gid = Column(String(255))
    resend_upcycle_section_gid = Column(String(255))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
