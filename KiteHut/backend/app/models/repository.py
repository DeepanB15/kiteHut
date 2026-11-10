from pydantic import BaseModel


class RepositoryInfo(BaseModel):
    name: str
    owner: str
    url: str
    local_path: str