"""Movie domain model backed by a Python 3.10+ dataclass."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any


@dataclass(slots=True)
class Movie:
    """Represents a movie retrieved from the TMDB API.

    Required fields must always be present; optional fields default to
    ``None`` and are omitted from dictionary output when unset.
    """

    id: int
    title: str
    release_date: str
    overview: str

    vote_average: float | None = None
    vote_count: int | None = None
    genres: list[str] | None = None
    poster_path: str | None = None
    runtime: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, int) or self.id <= 0:
            raise ValueError(f"id must be a positive integer, got {self.id!r}")
        if not self.title or not isinstance(self.title, str):
            raise ValueError("title must be a non-empty string")
        if not isinstance(self.release_date, str):
            raise ValueError("release_date must be a string")
        if not isinstance(self.overview, str):
            raise ValueError("overview must be a string")

    @classmethod
    def from_tmdb_response(cls, data: dict[str, Any]) -> Movie:
        """Construct a Movie from a raw TMDB API JSON dictionary.

        Handles both the ``/search/movie`` response shape (which provides
        ``genre_ids`` as a list of ints) and the ``/movie/{id}`` detail
        shape (which provides full ``genres`` objects with names).

        Args:
            data: A single movie object from the TMDB API.

        Returns:
            A validated Movie instance.

        Raises:
            ValueError: If required fields are missing or invalid.
        """
        raw_genres: list[str] | None = None
        if "genres" in data:
            raw_genres = [g["name"] for g in data["genres"] if "name" in g]
        elif "genre_ids" in data:
            # TODO: map genre IDs to names via /genre/movie/list
            raw_genres = [str(gid) for gid in data["genre_ids"]]

        return cls(
            id=data.get("id", 0),
            title=data.get("title", ""),
            release_date=data.get("release_date", ""),
            overview=data.get("overview", ""),
            vote_average=data.get("vote_average"),
            vote_count=data.get("vote_count"),
            genres=raw_genres or None,
            poster_path=data.get("poster_path"),
            runtime=data.get("runtime"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the movie to a plain dictionary.

        Keys whose value is ``None`` are excluded from the output so the
        result is compact and ready for JSON encoding.
        """
        return {k: v for k, v in asdict(self).items() if v is not None}
