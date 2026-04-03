# Feature: Chroma Repository

**Date:** 2026-04-02  
**Files Introduced:** 2  
**New Dependencies:** 0

---

## Summary

Adds a persistent `ChromaRepository` for storing and querying movie embeddings with ChromaDB. The repository lives under `movie-search/repositories/`, validates embedding dimensions against `EmbeddingService`, persists data to `movie-search/data/chroma/`, and exposes thread-safe CRUD and similarity search operations for semantic retrieval workflows.

## Files Introduced

- `movie-search/repositories/chroma_repository.py` — persistent ChromaDB repository with add, batch upsert, search, text-query search, lookup, delete, count, and reset support.
- `movie-search/tests/test_chroma_repository.py` — pytest coverage for upsert behavior, filtered search, persistence across instances, invalid dimensions, and reset.

## Files Updated

- `movie-search/repositories/__init__.py` — re-exports `ChromaRepository` and `ChromaRepositoryError`.
- `movie-search/.gitignore` — ignores the persistent Chroma data directory under `data/chroma/`.

## Dependencies Added

None. ChromaDB (`chromadb==1.5.5`) and SentenceTransformers were already listed in `movie-search/requirements.txt`.

## Usage Example

```python
from repositories.chroma_repository import ChromaRepository
from services.embedding_service import EmbeddingService

embedding_service = EmbeddingService()
repository = ChromaRepository(collection_name="movies")

text = "A hacker discovers reality is a simulation."
repository.add_movie(
    movie_id=1,
    text=text,
    embedding=embedding_service.embed_text(text),
    metadata={
        "title": "The Matrix",
        "year": 1999,
        "rating": 8.7,
        "genres": ["Action", "Sci-Fi"],
    },
)

results = repository.search_by_text("science fiction action movie", top_k=5)
for result in results:
    print(result["id"], result["distance"], result["metadata"]["title"])
```

## Notes

- The default persistent storage path is `movie-search/data/chroma/`.
- The repository implementation is aligned with ChromaDB 1.5.5 API behavior.
- Duplicate movie IDs are handled with Chroma upsert semantics.
- Search supports Chroma metadata filtering, for example `{"year": {"$gte": 2020}}` or `{"rating": {"$gte": 8.0}}`.
- Stored metadata is flattened into Chroma-compatible primitive values; iterable `genres` values are stored as a comma-separated string.
- `reset()` deletes and recreates the collection and is intended for tests and local development workflows.