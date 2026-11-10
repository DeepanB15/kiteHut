from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional


class RepositoryResponse(BaseModel):
    id: str
    name: str
    path: str
    created_at: Optional[datetime] = None
    last_indexed_at: Optional[datetime] = None
    status: Optional[str] = None
    total_files: Optional[int] = 0
    total_symbols: Optional[int] = 0
    error_message: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class RelationshipResponse(BaseModel):
    id: str
    repository_id: str
    source_symbol_id: str
    target_symbol_id: str
    relationship_type: str
    evidence_ref: Optional[dict] = None

    model_config = ConfigDict(from_attributes=True)
