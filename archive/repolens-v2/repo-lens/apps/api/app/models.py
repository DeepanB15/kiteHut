from sqlalchemy import (
    Column, String, Integer, Boolean, Text, DateTime, ForeignKey, JSON, Index
)
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime

Base = declarative_base()
from typing import Optional
import uuid


def _uuid() -> str:
    return str(uuid.uuid4())


class Repository(Base):
    __tablename__ = "repositories"
    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(512), nullable=False)
    path = Column(String(4096), nullable=False, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_indexed_at = Column(DateTime, nullable=True)
    status = Column(String(32), default="idle")
    total_files = Column(Integer, default=0)
    total_symbols = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)

    files = relationship("File", back_populates="repository", cascade="all, delete-orphan")
    symbols = relationship("Symbol", back_populates="repository", cascade="all, delete-orphan")
    relationships = relationship("Relationship", back_populates="repository", cascade="all, delete-orphan")
    findings = relationship("Finding", back_populates="repository", cascade="all, delete-orphan")
    git_commits = relationship("GitCommit", back_populates="repository", cascade="all, delete-orphan")


class File(Base):
    __tablename__ = "files"
    id = Column(String(36), primary_key=True, default=_uuid)
    repository_id = Column(String(36), ForeignKey("repositories.id"), nullable=False)
    path = Column(String(1024), nullable=False)
    language = Column(String(64), nullable=False)
    symbol_count = Column(Integer, default=0)
    is_test = Column(Boolean, default=False)
    parent_dir = Column(String(512), nullable=True)
    line_count = Column(Integer, default=0)

    repository = relationship("Repository", back_populates="files")
    symbols = relationship("Symbol", foreign_keys="Symbol.file_id", back_populates="file")

    __table_args__ = (Index("ix_repo_file", "repository_id", "path"),)


class SymbolType:
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    VARIABLE = "variable"
    CONSTANT = "constant"
    MODULE = "module"
    TYPE = "type"
    ENUM = "enum"

    ALL = (CLASS, FUNCTION, METHOD, VARIABLE, CONSTANT, MODULE, TYPE, ENUM)


class Symbol(Base):
    __tablename__ = "symbols"
    id = Column(String(36), primary_key=True, default=_uuid)
    repository_id = Column(String(36), ForeignKey("repositories.id"), nullable=False)
    symbol_type = Column(String(32), nullable=False)
    name = Column(String(512), nullable=False)
    file_path = Column(String(1024), nullable=False)
    file_id = Column(String(36), ForeignKey("files.id"), nullable=True)
    line_start = Column(Integer, nullable=True)
    line_end = Column(Integer, nullable=True)
    qualified_name = Column(String(1024), nullable=True)
    module_path = Column(String(1024), nullable=True)

    repository = relationship("Repository", back_populates="symbols")
    file = relationship("File", foreign_keys=[file_id], back_populates="symbols")
    calls = relationship("CallRelationship", foreign_keys="CallRelationship.callers_symbol_id", back_populates="source", cascade="all, delete-orphan")
    called_by = relationship("CallRelationship", foreign_keys="CallRelationship.callee_symbol_id", back_populates="callee", cascade="all, delete-orphan")
    imports = relationship("ImportRelationship", foreign_keys="ImportRelationship.symbol_id", back_populates="symbol", cascade="all, delete-orphan")
    imported_by = relationship("ImportRelationship", foreign_keys="ImportRelationship.importing_symbol_id", back_populates="importing_symbol", cascade="all, delete-orphan")
    depends_on = relationship("DependencyRelationship", foreign_keys="DependencyRelationship.dependent_symbol_id", back_populates="dependent", cascade="all, delete-orphan")
    depended_on_by = relationship("DependencyRelationship", foreign_keys="DependencyRelationship.depender_symbol_id", back_populates="depender", cascade="all, delete-orphan")
    tests = relationship("TestReference", foreign_keys="TestReference.symbol_id", back_populates="symbol", cascade="all, delete-orphan")

    __table_args__ = (Index("ix_sym_repo_name", "repository_id", "name"),)


class RelationshipType:
    CONTAINS = "contains"
    IMPORTS = "imports"
    EXPORTS = "exports"
    CALLS = "calls"
    DEFINES = "defines"
    TESTS = "tests"
    DEPENDS_ON = "depends_on"
    ROUTES_TO = "routes_to"
    READS_FROM = "reads_from"
    WRITES_TO = "writes_to"
    CHANGED_IN = "changed_in"

    ALL = (CONTAINS, IMPORTS, EXPORTS, CALLS, DEFINES, TESTS, DEPENDS_ON, ROUTES_TO, READS_FROM, WRITES_TO, CHANGED_IN)


class Relationship(Base):
    __tablename__ = "relationships"
    id = Column(String(36), primary_key=True, default=_uuid)
    repository_id = Column(String(36), ForeignKey("repositories.id"), nullable=False)
    source_symbol_id = Column(String(36), ForeignKey("symbols.id"), nullable=False)
    target_symbol_id = Column(String(36), ForeignKey("symbols.id"), nullable=False)
    relationship_type = Column(String(64), nullable=False)
    evidence_ref = Column(JSON, nullable=True)

    repository = relationship("Repository", back_populates="relationships")
    source_symbol = relationship("Symbol", foreign_keys=[source_symbol_id])
    target_symbol = relationship("Symbol", foreign_keys=[target_symbol_id])

    __table_args__ = (Index("ix_rels_pair", "source_symbol_id", "target_symbol_id", "relationship_type"),)


class CallRelationship(Base):
    __tablename__ = "call_relationships"
    id = Column(String(36), primary_key=True, default=_uuid)
    repository_id = Column(String(36), ForeignKey("repositories.id"), nullable=False)
    callers_symbol_id = Column(String(36), ForeignKey("symbols.id"), nullable=False)
    callee_symbol_id = Column(String(36), ForeignKey("symbols.id"), nullable=False)
    line_context = Column(JSON, nullable=True)

    repository = relationship("Repository")
    source = relationship("Symbol", foreign_keys=[callers_symbol_id], back_populates="calls")
    callee = relationship("Symbol", foreign_keys=[callee_symbol_id], back_populates="called_by")

    __table_args__ = (Index("ix_calls_pair", "callers_symbol_id", "callee_symbol_id"),)


class ImportRelationship(Base):
    __tablename__ = "import_relationships"
    id = Column(String(36), primary_key=True, default=_uuid)
    repository_id = Column(String(36), ForeignKey("repositories.id"), nullable=False)
    symbol_id = Column(String(36), ForeignKey("symbols.id"), nullable=False)
    importing_symbol_id = Column(String(36), ForeignKey("symbols.id"), nullable=False)
    import_path = Column(String(512), nullable=False)
    is_external = Column(Boolean, default=False)

    repository = relationship("Repository")
    symbol = relationship("Symbol", foreign_keys=[symbol_id], back_populates="imports")
    importing_symbol = relationship("Symbol", foreign_keys=[importing_symbol_id], back_populates="imported_by")

    __table_args__ = (Index("ix_imp_pair", "symbol_id", "importing_symbol_id"),)


class DependencyRelationship(Base):
    __tablename__ = "dependency_relationships"
    id = Column(String(36), primary_key=True, default=_uuid)
    repository_id = Column(String(36), ForeignKey("repositories.id"), nullable=False)
    dependent_symbol_id = Column(String(36), ForeignKey("symbols.id"), nullable=False)
    depender_symbol_id = Column(String(36), ForeignKey("symbols.id"), nullable=False)
    dependency_type = Column(String(64), nullable=False)

    repository = relationship("Repository")
    dependent = relationship("Symbol", foreign_keys=[dependent_symbol_id], back_populates="depends_on")
    depender = relationship("Symbol", foreign_keys=[depender_symbol_id], back_populates="depended_on_by")

    __table_args__ = (Index("ix_dep_pair", "dependent_symbol_id", "depender_symbol_id"),)


class TestReference(Base):
    __tablename__ = "test_references"
    id = Column(String(36), primary_key=True, default=_uuid)
    repository_id = Column(String(36), ForeignKey("repositories.id"), nullable=False)
    symbol_id = Column(String(36), ForeignKey("symbols.id"), nullable=False)
    test_file_path = Column(String(1024), nullable=False)
    test_file_id = Column(String(36), ForeignKey("files.id"), nullable=False)
    line_context = Column(JSON, nullable=True)

    repository = relationship("Repository")
    symbol = relationship("Symbol", foreign_keys=[symbol_id], back_populates="tests")

    __table_args__ = (Index("ix_tests_sym", "symbol_id"),)


class Finding(Base):
    __tablename__ = "findings"
    id = Column(String(36), primary_key=True, default=_uuid)
    repository_id = Column(String(36), ForeignKey("repositories.id"), nullable=False)
    category = Column(String(64), nullable=False)
    severity = Column(String(32), nullable=False)
    title = Column(String(512), nullable=False)
    description = Column(Text, nullable=True)
    confidence = Column(String(32), default="MEDIUM")
    evidence_refs = Column(JSON, nullable=True)
    intent_category = Column(String(32), nullable=True)
    ai_provider = Column(String(128), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    status = Column(String(32), default="OPEN")
    fix_proposal = Column(JSON, nullable=True)

    repository = relationship("Repository", back_populates="findings")
    fixes = relationship("FixProposal", back_populates="finding", cascade="all, delete-orphan")

    __table_args__ = (Index("ix_findings_cat", "repository_id", "category"),)


class FixProposalStatus:
    PROPOSED = "proposed"
    APPROVED = "approved"
    APPLIED = "applied"
    REJECTED = "rejected"
    VERIFIED = "verified"
    FAILED = "failed"
    ROLLBACK_NEEDED = "rollback_needed"


class FixProposal(Base):
    __tablename__ = "fix_proposals"
    id = Column(String(36), primary_key=True, default=_uuid)
    finding_id = Column(String(36), ForeignKey("findings.id"), nullable=False)
    status = Column(String(32), default="proposed")
    patch_diff = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    affected_files = Column(JSON, nullable=True)
    test_output = Column(Text, nullable=True)
    verification_result = Column(JSON, nullable=True)
    reviewed_by = Column(String(128), nullable=True)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    finding = relationship("Finding", back_populates="fixes")


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"
    id = Column(String(36), primary_key=True, default=_uuid)
    repository_id = Column(String(36), ForeignKey("repositories.id"), nullable=False)
    run_type = Column(String(64), nullable=False)
    files_analyzed = Column(Integer, default=0)
    duration_ms = Column(Integer, nullable=True)
    status = Column(String(32), default="running")
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    error_log = Column(Text, nullable=True)


class GitCommit(Base):
    __tablename__ = "git_commits"
    id = Column(String(36), primary_key=True, default=_uuid)
    repository_id = Column(String(36), ForeignKey("repositories.id"), nullable=False)
    hash = Column(String(64), nullable=False, index=True)
    author_name = Column(String(256), nullable=True)
    author_email = Column(String(256), nullable=True)
    date = Column(DateTime, nullable=True)
    message = Column(Text, nullable=True)
    changed_files = Column(JSON, nullable=True)
    symbol_changes = Column(JSON, nullable=True)
    is_indexed = Column(Boolean, default=False)

    repository = relationship("Repository", back_populates="git_commits")
