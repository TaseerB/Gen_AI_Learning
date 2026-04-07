"""Query expansion utilities for improving movie search recall.

This module provides `QueryExpander`, which takes a short user query and produces
up to `max_expansions` semantically related variations using a predefined synonym
dictionary, domain knowledge, and genre-aware expansions. Feeding these
variations into downstream search increases recall by catching queries that use
different vocabulary for the same concept.

Example:
    Basic expansion::

        from utils.query_expander import QueryExpander

        expander = QueryExpander()
        variations = expander.expand_query("funny space movie", max_expansions=3)
        # ["funny space movie", "comedy outer space movie", "humorous galaxy movie"]

    Only genre expansions::

        variations = expander.expand_query("action hero", max_expansions=2)
        # ["action hero", "action thriller hero"]
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dictionaries
# ---------------------------------------------------------------------------

SYNONYMS: dict[str, list[str]] = {
    # Mood / tone
    "funny": ["comedy", "humorous", "hilarious", "amusing"],
    "scary": ["horror", "frightening", "terrifying", "chilling"],
    "sad": ["emotional", "tearjerker", "tragic", "melancholic"],
    "happy": ["feel-good", "uplifting", "cheerful", "heartwarming"],
    "dark": ["gritty", "bleak", "sinister", "noir"],
    "exciting": ["thrilling", "gripping", "edge-of-your-seat", "intense"],
    "boring": ["slow-paced", "uneventful", "dull"],
    "beautiful": ["visually stunning", "gorgeous", "breathtaking"],
    # Narrative / character
    "smart": ["intelligent", "cerebral", "thought-provoking", "clever"],
    "romantic": ["love story", "romance", "relationship", "passionate"],
    "violent": ["brutal", "action-packed", "intense", "graphic"],
    "mysterious": ["suspenseful", "enigmatic", "cryptic", "whodunit"],
    "epic": ["grand", "sweeping", "blockbuster", "large-scale"],
    "classic": ["timeless", "iconic", "legendary", "acclaimed"],
    "weird": ["surreal", "bizarre", "unconventional", "experimental"],
    # Setting / domain
    "space": ["outer space", "galaxy", "universe", "cosmos"],
    "future": ["futuristic", "dystopian", "sci-fi", "post-apocalyptic"],
    "historical": ["period piece", "costume drama", "based on true story", "epic history"],
    "war": ["battle", "military", "combat", "wartime drama"],
    "ocean": ["sea", "underwater", "deep sea", "maritime"],
    "city": ["urban", "metropolitan", "city life", "street"],
    "village": ["rural", "countryside", "small town", "provincial"],
    # Common phrases
    "time travel": ["time machine", "temporal paradox", "alternate timeline"],
    "heist": ["robbery", "theft", "caper", "con artist"],
    "revenge": ["vengeance", "payback", "retribution", "justice"],
    "survival": ["post-apocalyptic", "wilderness survival", "disaster", "life or death"],
    "coming of age": ["growing up", "teen drama", "adolescence", "self-discovery"],
    "superhero": ["superpower", "comic book", "marvel", "dc"],
    "zombie": ["undead", "apocalypse", "infected", "outbreak"],
    "vampire": ["gothic horror", "supernatural", "undead", "bloodsucking"],
    "spy": ["espionage", "secret agent", "intelligence", "covert operations"],
    "detective": ["crime solving", "mystery", "investigation", "whodunit"],
    "magic": ["fantasy", "wizardry", "sorcery", "supernatural"],
    "dragon": ["fantasy", "mythical creatures", "medieval", "epic fantasy"],
    "robot": ["android", "artificial intelligence", "machine", "sci-fi"],
}

GENRE_EXPANSIONS: dict[str, list[str]] = {
    "action": ["action thriller", "action adventure"],
    "comedy": ["romantic comedy", "dark comedy", "comedy drama"],
    "horror": ["supernatural horror", "psychological horror", "slasher horror"],
    "drama": ["psychological drama", "character study", "indie drama"],
    "thriller": ["psychological thriller", "crime thriller", "political thriller"],
    "romance": ["romantic drama", "romantic comedy", "period romance"],
    "sci-fi": ["science fiction action", "sci-fi thriller", "space opera"],
    "fantasy": ["epic fantasy", "dark fantasy", "urban fantasy"],
    "mystery": ["crime mystery", "detective mystery", "thriller mystery"],
    "documentary": ["biographical documentary", "nature documentary", "crime documentary"],
    "animation": ["animated comedy", "animated adventure", "family animation"],
    "adventure": ["action adventure", "fantasy adventure", "survival adventure"],
    "crime": ["crime thriller", "crime drama", "heist film"],
    "western": ["classic western", "neo-western", "revisionist western"],
    "musical": ["musical drama", "musical comedy", "music biopic"],
    "war": ["anti-war drama", "military action", "war thriller"],
    "biography": ["biographical drama", "historical biopic", "true story"],
    "history": ["historical drama", "period piece", "historical epic"],
    "sport": ["sports drama", "underdog sport", "sports biography"],
}

KNOWN_GENRES: frozenset[str] = frozenset(GENRE_EXPANSIONS.keys())

# Pre-compile multi-word synonym patterns sorted longest-first to avoid partial replacements
_SORTED_SYNONYMS: list[tuple[str, list[str]]] = sorted(
    SYNONYMS.items(), key=lambda kv: len(kv[0].split()), reverse=True
)


class QueryExpander:
    """Expand natural language search queries with synonyms and genre-aware variations.

    The expander returns the original query first, then up to `max_expansions - 1`
    additional unique variations built from three strategies:

    1. **Synonym replacement** — swap one word or phrase with dictionary synonyms.
    2. **Domain expansions** — substitute recognised domain phrases (e.g. "space"
       becomes "outer space").
    3. **Genre expansions** — when the query contains a known genre keyword, add
       genre-qualified variants (e.g. "comedy" → "romantic comedy").

    All returned strings are lowercase, whitespace-normalised, and deduplicated.

    Example:
        >>> expander = QueryExpander()
        >>> expander.expand_query("funny space movie", max_expansions=4)
        ["funny space movie", "comedy outer space movie", "humorous cosmos movie", ...]
    """

    def expand_query(self, query: str, max_expansions: int = 3) -> list[str]:
        """Expand a search query into semantically related variations.

        Args:
            query: The original user query (e.g. "scary sci-fi movie").
            max_expansions: Total number of unique queries to return including the
                original. Must be at least 1.

        Returns:
            A list of up to `max_expansions` distinct query strings with the
            original query always in first position.

        Example:
            >>> expander = QueryExpander()
            >>> expander.expand_query("romantic drama", max_expansions=3)
            ['romantic drama', 'love story drama', 'romantic drama romantic drama']
        """
        if not isinstance(query, str) or not query.strip():
            logger.debug("Received empty query for expansion, returning empty list")
            return []

        effective_limit = max(1, max_expansions)
        normalized_original = self._normalize(query)
        seen: list[str] = [normalized_original]

        logger.info("Expanding query=%r (max_expansions=%s)", normalized_original, effective_limit)

        # Strategy A + B: synonym / domain replacements
        for candidate in self._replace_synonyms(normalized_original):
            if candidate not in seen:
                seen.append(candidate)
            if len(seen) >= effective_limit:
                break

        # Strategy C: genre-aware expansions
        if len(seen) < effective_limit:
            detected_genre = self._detect_genre(normalized_original)
            if detected_genre:
                for candidate in self._add_genre_expansions(normalized_original, detected_genre):
                    if candidate not in seen:
                        seen.append(candidate)
                    if len(seen) >= effective_limit:
                        break

        final = seen[:effective_limit]
        logger.debug("Expanded to %s variation(s): %s", len(final), final)
        return final

    def _detect_genre(self, query: str) -> str | None:
        """Check whether the query contains a known genre keyword.

        Args:
            query: Normalised query string.

        Returns:
            The matched genre name, or `None` if no genre is detected.

        Example:
            >>> expander._detect_genre("a scary action film")
            "action"
        """
        for genre in KNOWN_GENRES:
            if re.search(rf"\b{re.escape(genre)}\b", query, re.IGNORECASE):
                logger.debug("Detected genre=%r in query=%r", genre, query)
                return genre
        return None

    def _replace_synonyms(self, query: str) -> list[str]:
        """Generate query variations by replacing matched words with synonyms.

        Iterates over the synonym dictionary ordered longest-first (so multi-word
        phrases are tried before their component words), then generates one
        variation per synonym per matched key.

        Args:
            query: Normalised query string.

        Returns:
            List of unique query variations ordered by synonym position.

        Example:
            >>> expander._replace_synonyms("funny movie")
            ["comedy movie", "humorous movie", "hilarious movie", "amusing movie"]
        """
        variations: list[str] = []

        for term, synonyms in _SORTED_SYNONYMS:
            pattern = re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)
            if not pattern.search(query):
                continue

            logger.debug("Matched synonym key=%r in query=%r", term, query)
            for synonym in synonyms:
                variation = pattern.sub(synonym, query, count=1)
                normalized_variation = self._normalize(variation)
                if normalized_variation != query and normalized_variation not in variations:
                    variations.append(normalized_variation)

        return variations

    def _add_genre_expansions(self, query: str, genre: str) -> list[str]:
        """Inject genre-qualified variants into the query.

        If the genre already occupies the query verbatim, it is replaced with
        each genre expansion. Otherwise each expansion is appended as a
        qualifier prefix.

        Args:
            query: Normalised query string.
            genre: Detected genre name (must exist in ``GENRE_EXPANSIONS``).

        Returns:
            List of genre-expanded query variants.

        Example:
            >>> expander._add_genre_expansions("comedy movie", "comedy")
            ["romantic comedy movie", "dark comedy movie", "comedy drama movie"]
        """
        expansions = GENRE_EXPANSIONS.get(genre, [])
        if not expansions:
            return []

        pattern = re.compile(rf"\b{re.escape(genre)}\b", re.IGNORECASE)
        variants: list[str] = []

        for expanded_genre in expansions:
            if pattern.search(query):
                variation = pattern.sub(expanded_genre, query, count=1)
            else:
                variation = f"{expanded_genre} {query}"
            normalized_variation = self._normalize(variation)
            if normalized_variation not in variants:
                variants.append(normalized_variation)

        logger.debug(
            "Genre expansion genre=%r produced %s variant(s)", genre, len(variants)
        )
        return variants

    def _normalize(self, text: str) -> str:
        """Lowercase and collapse whitespace in a query string."""
        return re.sub(r"\s+", " ", text.strip().lower())
