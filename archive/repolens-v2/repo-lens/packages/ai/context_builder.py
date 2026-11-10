from pydantic import BaseModel
from typing import List, Dict, Any, Optional


class SubgraphNode(BaseModel):
    id: str
    name: str
    file: str
    lines: Optional[str] = None


class SubgraphEdge(BaseModel):
    from_id: str
    to_id: str
    type: str
    evidence: Optional[Dict] = None


class StructuredContext(BaseModel):
    intent: str = "UNDERSTAND"
    question: str = ""
    subgraph_nodes: List[SubgraphNode] = []
    subgraph_edges: List[SubgraphEdge] = []
    source_evidence: List[Dict] = []
    tests: List[Dict] = []
    artifact_type: str = "python"
    repo_summary: Dict = {}
