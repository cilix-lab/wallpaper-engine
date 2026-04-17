from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_ignore_empty=True,
    )

    unsplash_access_key: str = ""
    image_dir: str = "/data/images"
    db_path: str = "/data/metadata.db"
    default_source: str = "hybrid"
    port: int = 8000
    max_image_size_mb: int = 10
    unsplash_query: str = ""
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
