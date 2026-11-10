from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    db_host: str = Field(default="postgres", env="DB_HOST")
    db_port: int = Field(default=5432, env="DB_PORT")
    db_name: str = Field(default="repolens", env="DB_NAME")
    db_user: str = Field(default="repolens", env="DB_USER")
    db_password: str = Field(default="repolens", env="DB_PASSWORD")
    db_echo: bool = Field(default=False, env="DB_ECHO")

    ollama_host: str = Field(default="http://localhost:11434", env="OLLAMA_HOST")
    ollama_model: str = Field(default="qwen2.5-coder:7b", env="OLLAMA_MODEL")
    llm_provider: str = Field(default="ollama", env="LLM_PROVIDER")
    llm_timeout: int = Field(default=60, env="LLM_TIMEOUT")

    api_port: int = Field(default=8000, env="API_PORT")
    env: str = Field(default="development", env="ENV")
    log_level: str = Field(default="INFO", env="LOG_LEVEL")

    @property
    def database_url(self) -> str:
        return (
            f"postgresql://{self.db_user}:{self.db_password}@"
            f"{self.db_host}:{self.db_port}/{self.db_name}"
        )

    class Config:
        env_file = ".env"


settings = Settings()
