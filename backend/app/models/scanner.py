from collections import Counter
from typing import Dict, List

from pydantic import BaseModel


class ImportantFile(BaseModel):
    path: str
    category: str


class DirectoryInfo(BaseModel):
    path: str
    category: str


class ScanResult(BaseModel):
    total_files: int
    total_directories: int

    extensions: Dict[str, int]
    languages: Dict[str, int]

    important_files: List[ImportantFile]
    directories: List[DirectoryInfo]