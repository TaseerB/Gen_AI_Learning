from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from models.movie import Movie
from repositories.movie_repository import MovieRepository


@pytest.fixture
def test_db() -> sqlite3.Connection:
    """Create an isolated in-memory SQLite database with schema loaded."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    schema_path = APP_ROOT / "database" / "schema.sql"
    conn.executescript(schema_path.read_text(encoding="utf-8"))

    yield conn
    conn.close()


@pytest.fixture
def test_repository(test_db: sqlite3.Connection) -> MovieRepository:
    """Provide a MovieRepository wired to the test in-memory DB."""
    return MovieRepository(connection=test_db)


@pytest.fixture
def sample_movies() -> list[Movie]:
    """Reusable movie records for repository tests."""
    return [
        Movie(
            id=1,
            title="The Matrix",
            release_date="1999-03-31",
            overview="A hacker discovers reality is a simulation.",
            vote_average=8.7,
            vote_count=21000,
            genres=["Action", "Sci-Fi"],
            poster_path="/matrix.jpg",
            runtime=136,
        ),
        Movie(
            id=2,
            title="The Matrix Reloaded",
            release_date="2003-05-15",
            overview="Neo and allies continue the fight against machines.",
            vote_average=7.2,
            vote_count=12000,
            genres=["Action", "Sci-Fi"],
            poster_path="/matrix-reloaded.jpg",
            runtime=138,
        ),
        Movie(
            id=3,
            title="Inception",
            release_date="2010-07-16",
            overview="A thief enters dreams to steal secrets.",
            vote_average=8.8,
            vote_count=30000,
            genres=["Action", "Thriller"],
            poster_path="/inception.jpg",
            runtime=148,
        ),
    ]
