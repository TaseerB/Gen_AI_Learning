from __future__ import annotations

from models.movie import Movie
from repositories.movie_repository import MovieRepository


def test_save_and_find_by_id(test_repository: MovieRepository, sample_movies: list[Movie]) -> None:
    movie = sample_movies[0]

    test_repository.save(movie)
    retrieved = test_repository.find_by_id(movie.id)

    assert retrieved is not None
    assert retrieved.id == movie.id
    assert retrieved.title == movie.title
    assert retrieved.release_date == movie.release_date
    assert retrieved.overview == movie.overview
    assert retrieved.vote_average == movie.vote_average
    assert retrieved.vote_count == movie.vote_count
    assert retrieved.genres == movie.genres
    assert retrieved.poster_path == movie.poster_path
    assert retrieved.runtime == movie.runtime


def test_find_by_title(test_repository: MovieRepository, sample_movies: list[Movie]) -> None:
    for movie in sample_movies:
        test_repository.save(movie)

    results = test_repository.find_by_title("matrix")

    assert len(results) == 2
    assert [movie.title for movie in results] == ["The Matrix", "The Matrix Reloaded"]


def test_duplicate_handling(test_repository: MovieRepository, sample_movies: list[Movie]) -> None:
    movie = sample_movies[0]

    test_repository.save(movie)
    test_repository.save(movie)

    assert test_repository.count() == 1


def test_find_by_rating_range(test_repository: MovieRepository, sample_movies: list[Movie]) -> None:
    for movie in sample_movies:
        test_repository.save(movie)

    results = test_repository.find_by_rating_range(min_rating=8.0, max_rating=8.8)

    assert {movie.title for movie in results} == {"The Matrix", "Inception"}
    assert all(8.0 <= (movie.vote_average or 0.0) <= 8.8 for movie in results)
