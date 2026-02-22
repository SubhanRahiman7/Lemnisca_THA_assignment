"""App config from environment."""
import os
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    groq_api_key: str = ""
    docs_dir: Path = Path(__file__).resolve().parent.parent / "docs"
    port: int = 8000

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


def get_settings() -> Settings:
    # Allow DOCS_DIR override (e.g. for submission use ./docs)
    docs = os.environ.get("DOCS_DIR")
    s = Settings()
    if docs:
        s.docs_dir = Path(docs).resolve()  # e.g. for deploy: DOCS_DIR=/app/docs
    # Env var always overrides .env so export GROQ_API_KEY works on EC2 / server
    if os.environ.get("GROQ_API_KEY"):
        s.groq_api_key = os.environ["GROQ_API_KEY"]
    return s
