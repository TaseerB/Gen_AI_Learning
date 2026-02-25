"""Application settings loaded from environment variables."""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Configuration for the movie search application.

    Reads values from a .env file at the project root. The TMDB API key
    is required; the application will refuse to start without one.
    """

    tmdb_api_key: str
    tmdb_base_url: str = "https://api.themoviedb.org/3"
    debug: bool = False

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @field_validator("tmdb_api_key")
    @classmethod
    def api_key_must_be_set(cls, value: str) -> str:
        if not value or value == "your_key_here":
            raise ValueError(
                "TMDB_API_KEY is not configured. "
                "Get a free key at https://www.themoviedb.org/settings/api "
                "and add it to your .env file."
            )
        return value


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance.

    Raises:
        ValidationError: If required settings (e.g. TMDB_API_KEY) are missing
            or still set to placeholder values.
    """
    return Settings()
