import sys, os
sys.path.insert(0, r"C:\Users\Deepan B\Desktop\codez\repo-lens\packages")
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from pathlib import Path
from app.database import get_db
from app.schemas import RepositoryResponse, RelationshipResponse
from app.models import Repository, Relationship
import sys, os
sys.path.insert(0, r"C:\Users\Deepan B\Desktop\codez\repo-lens\packages")
from ingestion.index_service import IndexingService

router = APIRouter()

class IndexRequest(BaseModel):
    path: str

class IndexResponse(BaseModel):
    repository_id: str
    repository_path: str
    files_indexed: int
    supported_files: int
    unsupported_files: list
    symbols_indexed: int
    relationships_indexed: int
    duration_seconds: float


@router.get("/repositories", response_model=list[RepositoryResponse])
def list_repositories(db: Session = Depends(get_db)):
    repos = db.query(Repository).all()
    return repos


@router.get("/graph/{repository_id}", response_model=list[RelationshipResponse])
def graph(repository_id: str, db: Session = Depends(get_db)):
    rels = db.query(Relationship).filter(Relationship.repository_id == repository_id).all()
    return rels


@router.post("/repositories/index", response_model=IndexResponse)
def index_repository(req: IndexRequest, db: Session = Depends(get_db)):
    path = Path(req.path).resolve()
    # Path traversal / validation guard
    if not path.exists() or not path.is_dir():
        raise HTTPException(status_code=400, detail=f"Invalid path: {req.path}")
    # Prevent arbitrary shell commands: only directory paths allowed, no commands
    service = IndexingService(db=db)
    result = service.index_repository(str(path))
    return result
