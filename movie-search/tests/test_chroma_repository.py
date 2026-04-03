from __future__ import annotations

import repositories.chroma_repository as chroma_repository_module


class _FakeEmbeddingService:
    def get_embedding_dimension(self) -> int:
        return 3

    def embed_text(self, text: str) -> list[float]:
        normalized = text.lower().strip()
        if "matrix" in normalized:
            return [1.0, 0.0, 0.0]
        if "dream" in normalized or "inception" in normalized:
            return [0.0, 1.0, 0.0]
        return [0.0, 0.0, 1.0]


def test_add_get_delete_and_count(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(chroma_repository_module, "EmbeddingService", _FakeEmbeddingService)
    repository = chroma_repository_module.ChromaRepository(
        collection_name="movies_test_basic",
        persist_directory=str(tmp_path / "chroma"),
    )
    repository.reset()

    repository.add_movie(
        movie_id=1,
        text="A hacker discovers reality is a simulation.",
        embedding=[1.0, 0.0, 0.0],
        metadata={
            "title": "The Matrix",
            "year": 1999,
            "rating": 8.7,
            "genres": ["Action", "Sci-Fi"],
        },
    )

    stored = repository.get_by_id(1)

    assert stored is not None
    assert stored["id"] == 1
    assert stored["metadata"]["title"] == "The Matrix"
    assert stored["metadata"]["genres"] == "Action, Sci-Fi"
    assert repository.count() == 1
    assert repository.delete(1) is True
    assert repository.delete(1) is False
    assert repository.count() == 0


def test_add_movie_upsert_updates_existing_record(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(chroma_repository_module, "EmbeddingService", _FakeEmbeddingService)
    repository = chroma_repository_module.ChromaRepository(
        collection_name="movies_test_upsert",
        persist_directory=str(tmp_path / "chroma"),
    )
    repository.reset()

    repository.add_movie(
        movie_id=7,
        text="Initial description.",
        embedding=[1.0, 0.0, 0.0],
        metadata={
            "title": "Old Title",
            "year": 1999,
            "rating": 8.1,
            "genres": ["Action"],
        },
    )
    repository.add_movie(
        movie_id=7,
        text="Updated description.",
        embedding=[0.0, 1.0, 0.0],
        metadata={
            "title": "New Title",
            "year": 2000,
            "rating": 8.9,
            "genres": ["Sci-Fi"],
        },
    )

    stored = repository.get_by_id(7)

    assert stored is not None
    assert stored["text"] == "Updated description."
    assert stored["metadata"]["title"] == "New Title"
    assert repository.count() == 1


def test_add_movies_batch_and_search_with_filters(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(chroma_repository_module, "EmbeddingService", _FakeEmbeddingService)
    repository = chroma_repository_module.ChromaRepository(
        collection_name="movies_test_batch",
        persist_directory=str(tmp_path / "chroma"),
    )
    repository.reset()

    repository.add_movies_batch(
        [
            {
                "id": 1,
                "text": "A hacker discovers reality is a simulation.",
                "embedding": [1.0, 0.0, 0.0],
                "metadata": {
                    "title": "The Matrix",
                    "year": 1999,
                    "rating": 8.7,
                    "genres": ["Action", "Sci-Fi"],
                },
            },
            {
                "id": 2,
                "text": "Neo returns to fight the machines.",
                "embedding": [0.8, 0.2, 0.0],
                "metadata": {
                    "title": "The Matrix Reloaded",
                    "year": 2003,
                    "rating": 7.2,
                    "genres": ["Action", "Sci-Fi"],
                },
            },
            {
                "id": 3,
                "text": "A thief enters dreams to steal secrets.",
                "embedding": [0.0, 1.0, 0.0],
                "metadata": {
                    "title": "Inception",
                    "year": 2010,
                    "rating": 8.8,
                    "genres": ["Action", "Thriller"],
                },
            },
        ]
    )

    results = repository.search([1.0, 0.0, 0.0], top_k=2)
    filtered_results = repository.search(
        [1.0, 0.0, 0.0],
        top_k=5,
        filter_dict={"rating": {"$gte": 8.0}},
    )

    assert len(results) == 2
    assert results[0]["id"] == 1
    assert results[0]["distance"] == 0.0
    assert {result["id"] for result in filtered_results} == {1, 3}


def test_search_by_text_and_persistence_across_instances(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(chroma_repository_module, "EmbeddingService", _FakeEmbeddingService)
    persist_directory = str(tmp_path / "chroma")

    repository = chroma_repository_module.ChromaRepository(
        collection_name="movies_test_persist",
        persist_directory=persist_directory,
    )
    repository.reset()
    repository.add_movie(
        movie_id=11,
        text="A hacker discovers reality is a simulation.",
        embedding=[1.0, 0.0, 0.0],
        metadata={
            "title": "The Matrix",
            "year": 1999,
            "rating": 8.7,
            "genres": ["Action", "Sci-Fi"],
        },
    )

    reopened = chroma_repository_module.ChromaRepository(
        collection_name="movies_test_persist",
        persist_directory=persist_directory,
    )
    results = reopened.search_by_text("matrix simulation", top_k=1)

    assert reopened.count() == 1
    assert reopened.get_by_id(11) is not None
    assert results[0]["id"] == 11


def test_invalid_embedding_dimension_raises_error(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(chroma_repository_module, "EmbeddingService", _FakeEmbeddingService)
    repository = chroma_repository_module.ChromaRepository(
        collection_name="movies_test_dimension",
        persist_directory=str(tmp_path / "chroma"),
    )
    repository.reset()

    try:
        repository.add_movie(
            movie_id=99,
            text="Invalid embedding.",
            embedding=[1.0, 0.0],
            metadata={
                "title": "Broken",
                "year": 2024,
                "rating": 1.0,
                "genres": ["Drama"],
            },
        )
    except chroma_repository_module.ChromaRepositoryError as exc:
        assert "dimension" in str(exc).lower()
    else:
        raise AssertionError("Expected ChromaRepositoryError for invalid embedding dimension")


def test_reset_clears_collection(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(chroma_repository_module, "EmbeddingService", _FakeEmbeddingService)
    repository = chroma_repository_module.ChromaRepository(
        collection_name="movies_test_reset",
        persist_directory=str(tmp_path / "chroma"),
    )
    repository.reset()
    repository.add_movie(
        movie_id=5,
        text="Reset me.",
        embedding=[0.0, 0.0, 1.0],
        metadata={
            "title": "Resettable",
            "year": 2022,
            "rating": 6.1,
            "genres": ["Drama"],
        },
    )

    repository.reset()

    assert repository.count() == 0
    assert repository.get_by_id(5) is None