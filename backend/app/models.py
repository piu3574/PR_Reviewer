from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class PullRequest(Base):
    __tablename__ = "pull_requests"

    id = Column(Integer, primary_key=True, index=True)
    repo_name = Column(String, nullable=False)
    pr_number = Column(Integer, nullable=False)
    title = Column(String, nullable=False)
    author = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    files = relationship("File", back_populates="pull_request")
    analysis_results = relationship("AnalysisResult", back_populates="pull_request")
    issues = relationship("Issue", back_populates="pull_request")


class File(Base):
    __tablename__ = "files"

    id = Column(Integer, primary_key=True, index=True)
    pull_request_id = Column(Integer, ForeignKey("pull_requests.id"), nullable=False)
    filename = Column(String, nullable=False)
    diff = Column(Text, nullable=True)

    pull_request = relationship("PullRequest", back_populates="files")


class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id = Column(Integer, primary_key=True, index=True)
    pull_request_id = Column(Integer, ForeignKey("pull_requests.id"), nullable=False)
    quality_score = Column(Float, nullable=True)
    security_risk = Column(String, nullable=True)
    maintainability_score = Column(Float, nullable=True)
    verdict = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    pull_request = relationship("PullRequest", back_populates="analysis_results")


class Issue(Base):
    __tablename__ = "issues"

    id = Column(Integer, primary_key=True, index=True)
    pull_request_id = Column(Integer, ForeignKey("pull_requests.id"), nullable=False)
    file_name = Column(String, nullable=True)
    line_number = Column(Integer, nullable=True)
    issue_type = Column(String, nullable=True)   # e.g. "bug", "security", "style"
    severity = Column(String, nullable=True)     # e.g. "low", "medium", "high"
    source = Column(String, nullable=False)      # "static" or "ai"
    description = Column(Text, nullable=False)

    pull_request = relationship("PullRequest", back_populates="issues")