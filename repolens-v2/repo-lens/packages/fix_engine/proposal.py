from pydantic import BaseModel
from typing import Optional, List, Dict, Any


class FixProposal(BaseModel):
    finding_id: str
    patch_diff: Optional[str] = None
    description: Optional[str] = None
    affected_files: List[str] = []
    status: str = "proposed"  # proposed / approved / applied / verified / rejected / failed
    review_comment: Optional[str] = None
    test_result: Optional[Any] = None
    verification_result: Optional[Any] = None
    approved_by: Optional[str] = None
