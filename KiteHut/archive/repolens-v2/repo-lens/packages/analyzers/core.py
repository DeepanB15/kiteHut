from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from pathlib import Path


class SymbolInfo(BaseModel):
    symbol_type: str
    name: str
    file_path: str
    line_start: int = 0
    line_end: int = 0
    qualified_name: Optional[str] = None
    module_path: Optional[str] = None


class RelationshipInfo(BaseModel):
    source_symbol: Optional[str] = None
    target_symbol: Optional[str] = None
    relationship_type: str
    evidence_ref: Optional[Dict[str, Any]] = None


class ImportInfo(BaseModel):
    symbol_path: str
    import_path: str
    is_external: bool = False


class TestReferenceInfo(BaseModel):
    file_path: str
    line_start: int = 0
    line_end: int = 0
    symbol_name: Optional[str] = None


class AnalysisResult(BaseModel):
    file_path: str
    language: str
    symbols: List[SymbolInfo] = []
    relationships: List[RelationshipInfo] = []
    imports: List[ImportInfo] = []
    tests: List[TestReferenceInfo] = []
    line_count: int = 0
    error: Optional[str] = None
