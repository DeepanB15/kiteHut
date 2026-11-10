from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from enum import Enum


class EvidenceType(str, Enum):
    OBSERVATION = "observation"
    DERIVED = "derived"
    INFERENCE = "inference"


class EvidenceItem(BaseModel):
    repository_path: Optional[str] = None
    file_path: Optional[str] = None
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    symbol_name: Optional[str] = None
    relationship_type: Optional[str] = None
    git_commit: Optional[str] = None
    analyzer: Optional[str] = None
    evidence_type: EvidenceType = EvidenceType.OBSERVATION
    timestamp: Optional[str] = None
    confidence: str = "MEDIUM"


class FindingCategory(str, Enum):
    ARCHITECTURE = "architecture"
    SECURITY = "security"
    QUALITY = "quality"
    DEPENDENCY = "dependency"
    TESTING = "testing"


class FindingSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FindingStatus(str, Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    FALSE_POSITIVE = "false_positive"
    FIX_PROPOSED = "fix_proposed"
    APPROVED = "approved"
    FIXED = "fixed"
    VERIFIED = "verified"


class Finding(BaseModel):
    id: Optional[str] = None
    repository_id: str
    category: FindingCategory
    severity: FindingSeverity
    title: str
    description: Optional[str] = None
    confidence: str = "MEDIUM"
    status: FindingStatus = FindingStatus.OPEN
    evidence_refs: List[EvidenceItem] = []
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    fix_proposal_id: Optional[str] = None
