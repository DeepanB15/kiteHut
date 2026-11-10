"""
Phase 5 — Review Finding Model.
Evidence-based. Severity = impact × evidence_quality.
Category: security | quality | architecture.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"

class Category(str, Enum):
    SECURITY = "security"
    QUALITY = "quality"
    ARCHITECTURE = "architecture"

@dataclass
class Evidence:
    file_path: str
    line_start: int
    line_end: int
    snippet: str
    context: str = ""
    # Phase 6 — Evidence source tracking
    source_type: str = "repository_file"
    rule_id: str = ""
    repository_state_reference: str = ""

@dataclass
class Finding:
    category: Category
    severity: Severity
    title: str
    description: str
    evidence: List[Evidence] = field(default_factory=list)
    rule_id: str = ""
    source_file: Optional[str] = None
    # Phase 6 — Evidence & Evaluation metadata
    verification_status: str = "inconclusive"
    evidence_quality: str = "weak"
    confidence: str = "low"

    def severity_score(self) -> int:
        mapping = {Severity.CRITICAL: 4, Severity.HIGH: 3, Severity.MEDIUM: 2, Severity.LOW: 1, Severity.INFO: 0}
        return mapping[self.severity]

    def has_evidence(self) -> bool:
        return len(self.evidence) > 0
