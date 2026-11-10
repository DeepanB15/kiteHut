"""
Claim Models for RepoLens Verification Engine.
"""

from enum import Enum
from typing import Any, Dict, Optional
import uuid
from pydantic import BaseModel, Field


class ClaimType(str, Enum):
    """Types of falsifiable claims extracted from specialist findings."""
    FILE_EXISTS = "FILE_EXISTS"
    CODE_CONTAINS_PATTERN = "CODE_CONTAINS_PATTERN"
    AST_SYMBOL_EXISTS = "AST_SYMBOL_EXISTS"
    CONFIG_KEY_MISSING = "CONFIG_KEY_MISSING"
    UNTESTED_MODULE = "UNTESTED_MODULE"
    CIRCULAR_IMPORT = "CIRCULAR_IMPORT"
    SECRET_PATTERN_MATCH = "SECRET_PATTERN_MATCH"
    SQL_INJECTION_PATTERN = "SQL_INJECTION_PATTERN"
    UNPINNED_DEPENDENCY = "UNPINNED_DEPENDENCY"
    GIT_DIFF_CONTAINS = "GIT_DIFF_CONTAINS"
    HIGH_COMPLEXITY = "HIGH_COMPLEXITY"
    GENERIC = "GENERIC"


class ExtractedClaim(BaseModel):
    """Atomic, falsifiable proposition that requires evidence verification."""
    claim_id: str = Field(default_factory=lambda: f"clm_{uuid.uuid4().hex[:8]}")
    claim_type: ClaimType
    statement: str
    target_file: Optional[str] = None
    target_line: Optional[int] = None
    expected_pattern: Optional[str] = None
    context_data: Dict[str, Any] = Field(default_factory=dict)
