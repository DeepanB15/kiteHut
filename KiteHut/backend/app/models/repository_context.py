from typing import Dict, List

from pydantic import BaseModel


class FileReference(BaseModel):
    path: str
    category: str


class ProjectStructure(BaseModel):
    source_directories: List[str]
    test_directories: List[str]
    frontend_directories: List[str]
    documentation_directories: List[str]
    configuration_directories: List[str]
    application_components: List[str]


class RepositoryStatistics(BaseModel):
    total_files: int
    total_directories: int
    extensions: Dict[str, int]


class RepositoryContext(BaseModel):
    repository_name: str
    repository_owner: str
    repository_url: str

    statistics: RepositoryStatistics

    languages: Dict[str, int]

    technologies: List[str]

    important_files: List[FileReference]

    entry_points: List[str]

    structure: ProjectStructure
