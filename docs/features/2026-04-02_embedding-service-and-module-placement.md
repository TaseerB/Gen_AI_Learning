# Feature: Embedding Service and Module Placement

**Date:** 2026-04-02  
**Files Introduced:** 1  
**New Dependencies:** 0

---

## Summary

Adds a thread-safe singleton `EmbeddingService` backed by SentenceTransformers (`all-MiniLM-L6-v2`) to generate normalized vector embeddings for semantic workflows. The implementation now lives inside the `movie-search/services/` layer to keep runtime code within the application boundary and avoid creating ad-hoc top-level Python packages.

## Files Introduced

- `movie-search/services/embedding_service.py` — Singleton embedding service with model loading, input normalization, single/batch embedding APIs, and robust logging/error handling.

## Files Updated

- `movie-search/services/__init__.py` — Re-exports `EmbeddingService`.
- `.github/copilot-instructions.md` — Adds a project-structure rule requiring new runtime Python modules to be placed under `movie-search/` in the closest existing layer (`services/`, `repositories/`, `models/`, `database/`, `ui/`) unless explicitly requested otherwise.

## Dependencies Added

None. (`sentence-transformers` already existed in `movie-search/requirements.txt`.)

## Usage Example

```python
from services.embedding_service import EmbeddingService

service = EmbeddingService()

single = service.embed_text("A noir detective story set in Los Angeles")
print(len(single))  # 384

batch = service.embed_batch([
    "Cyberpunk action thriller",
    "Warm family comedy",
])
print(len(batch), len(batch[0]))  # 2 384

print(service.get_embedding_dimension())  # 384
```

## Notes

- `EmbeddingService` uses a singleton pattern so only one model instance is loaded in memory.
- `embed_text` and `embed_batch` return unit-normalized vectors.
- Empty/invalid text input returns a zero vector.
- Batch encoding shows a progress bar when more than 10 texts are passed.
- Input text normalization lowercases, removes extra whitespace, and truncates to 512 whitespace tokens with a warning log when truncated.
