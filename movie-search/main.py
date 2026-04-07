"""CLI entry point for the movie search application."""

from __future__ import annotations

import logging
import random
import sys
from typing import Any

from pydantic import ValidationError
from rich.console import Console
from rich.panel import Panel
from rich.progress import track
from rich.table import Table

from config.settings import get_settings
from database.connection import initialize_database
from importer import run_import_flow
from models.movie import Movie
from repositories.chroma_repository import ChromaRepository, ChromaRepositoryError
from repositories.movie_repository import MovieRepository, RepositoryError
from search.hybrid_search import HybridSearchEngine, HybridSearchError
from search.reranker import SearchReranker, SearchRerankerError
from ui.display import display_movie_details, render_movie_table
from utils.query_expander import QueryExpander
from services.embedding_service import EmbeddingService

console = Console()

GENRE_INTENT_KEYWORDS: dict[str, str] = {
    "action": "Action",
    "adventure": "Adventure",
    "comedy": "Comedy",
    "funny": "Comedy",
    "romance": "Romance",
    "romantic": "Romance",
    "drama": "Drama",
    "thriller": "Thriller",
    "horror": "Horror",
    "scary": "Horror",
    "sci-fi": "Sci-Fi",
    "scifi": "Sci-Fi",
    "science fiction": "Sci-Fi",
    "fantasy": "Fantasy",
    "animation": "Animation",
    "crime": "Crime",
    "mystery": "Mystery",
}


def _extract_genre_intent_from_query(query: str) -> list[str]:
    """Extract likely genre intent terms from free-text query."""
    normalized = query.lower()
    detected: list[str] = []
    for keyword, genre in GENRE_INTENT_KEYWORDS.items():
        if keyword in normalized and genre not in detected:
            detected.append(genre)
    return detected


def _ensure_embeddings_available() -> ChromaRepository | None:
    """Safely initialize ChromaRepository and return it, or None if unavailable."""
    try:
        chroma = ChromaRepository()
        if chroma.count() == 0:
            console.print("[bold yellow]Warning:[/] ChromaDB has no embeddings.")
            console.print("[bold yellow]Populate with:[/] python scripts/populate_embeddings.py\n")
            return None
        return chroma
    except ChromaRepositoryError as exc:
        console.print(f"[bold red]ChromaDB unavailable:[/] {exc}\n")
        return None


def _simple_search(repo: MovieRepository, engine: HybridSearchEngine) -> None:
    """Option 1: Simple semantic-only search."""
    console.print(
        Panel(
            "[bold cyan]Simple Search[/]\nFind movies using natural language queries.\n"
            "[dim]Examples:[/] movies about time travel, romantic comedies, sci-fi thrillers",
            border_style="cyan",
        )
    )
    query = console.input("[bold yellow]Enter your query:[/] ").strip()
    if not query:
        console.print("[bold red]Query cannot be empty.[/]\n")
        return

    try:
        with console.status("[bold cyan]Searching..."):
            results = engine.search(query=query, top_k=10, ranking_strategy="semantic")
    except HybridSearchError as exc:
        console.print(f"[bold red]Search failed:[/] {exc}\n")
        return

    if not results:
        console.print("[bold yellow]No results found. Try a different query.[/]\n")
        return

    _display_and_detail_results("Simple Search Results", results)


def _advanced_search(repo: MovieRepository, engine: HybridSearchEngine, expander: QueryExpander) -> None:
    """Option 2: Advanced search with filters, expansion, and reranking."""
    console.print(
        Panel(
            "[bold magenta]Advanced Search[/]\n"
            "Find movies with custom filters and ranking strategies.\n"
            "[dim]Tip:[/] Start with broad filters first, then tighten.",
            border_style="magenta",
        )
    )

    console.print(
        "[dim]Try queries:[/]\n"
        "  - space adventure\n"
        "  - mind bending thriller\n"
        "  - funny family movie\n"
        "  - romantic drama"
    )

    query = console.input("[bold yellow]Enter your query:[/] ").strip()
    if not query:
        console.print("[bold red]Query cannot be empty.[/]\n")
        return

    console.print("\n[bold]Optional Filters[/] (press Enter to skip any):")
    min_rating_raw = console.input("  Min rating (0-10) [skip]: ").strip()
    max_rating_raw = console.input("  Max rating (0-10) [skip]: ").strip()
    min_year_raw = console.input("  Min year [skip]: ").strip()
    max_year_raw = console.input("  Max year [skip]: ").strip()
    console.print(
        "  [dim]Genre examples:[/] Action, Adventure, Comedy, Drama, Thriller, Sci-Fi, "
        "Romance, Horror, Fantasy, Animation"
    )
    genres_raw = console.input("  Genres comma-separated [skip]: ").strip()

    filters: dict[str, Any] = {}
    try:
        if min_rating_raw:
            filters["min_rating"] = float(min_rating_raw)
        if max_rating_raw:
            filters["max_rating"] = float(max_rating_raw)
        if min_year_raw:
            filters["min_year"] = int(min_year_raw)
        if max_year_raw:
            filters["max_year"] = int(max_year_raw)
        if genres_raw:
            filters["genres"] = [g.strip() for g in genres_raw.split(",") if g.strip()]
    except ValueError:
        console.print("[bold red]Invalid filter values.[/]\n")
        return

    inferred_genres = _extract_genre_intent_from_query(query)
    if "genres" not in filters and inferred_genres:
        filters["genres"] = inferred_genres
        console.print(
            f"[dim]Detected genre intent from query:[/] {', '.join(inferred_genres)}"
        )

    # Normalize obvious user input mistakes to avoid accidental zero-result searches.
    if "min_rating" in filters and "max_rating" in filters:
        if filters["min_rating"] > filters["max_rating"]:
            filters["min_rating"], filters["max_rating"] = filters["max_rating"], filters["min_rating"]

    if "min_year" in filters and "max_year" in filters:
        if filters["min_year"] > filters["max_year"]:
            filters["min_year"], filters["max_year"] = filters["max_year"], filters["min_year"]

    console.print("\n[bold]Ranking Strategy:[/]")
    console.print("  1. Semantic (embedding similarity)")
    console.print("  2. Quality First (rating-focused)")
    console.print("  3. Trending (popularity + recency)")
    console.print("  4. Balanced (all signals)")
    strategy_choice = console.input("[bold yellow]Choose (1-4) [4]:[/] ").strip() or "4"
    debug_trace = (
        console.input("[bold yellow]Show debug trace (expanded queries + stage counts)? [y/N]:[/] ")
        .strip()
        .lower()
        in {"y", "yes"}
    )
    strategy_mapping = {
        # (HybridSearchEngine strategy, SearchReranker strategy)
        "1": ("semantic", "balanced"),
        "2": ("rating", "quality_first"),
        "3": ("recency", "trending"),
        "4": ("hybrid", "balanced"),
    }
    engine_strategy, reranker_strategy = strategy_mapping.get(strategy_choice, ("hybrid", "balanced"))

    try:
        with console.status("[bold cyan]Expanding query..."):
            expanded_queries = expander.expand_query(query, max_expansions=3)

        if debug_trace:
            console.print(f"[dim]Expanded queries:[/] {', '.join(expanded_queries)}")

        # Progressive relaxation so users still get results when filters are too strict.
        filter_stages: list[tuple[str, dict[str, Any] | None]] = []
        active_filters = filters if filters else None
        filter_stages.append(("your exact filters", active_filters))

        if active_filters:
            # Relax year before genre to keep semantic intent aligned longer.
            no_year_filters = dict(active_filters)
            no_year_filters.pop("min_year", None)
            no_year_filters.pop("max_year", None)
            filter_stages.append(("without year filter", no_year_filters or None))

            no_rating_filters = dict(no_year_filters)
            no_rating_filters.pop("min_rating", None)
            no_rating_filters.pop("max_rating", None)
            filter_stages.append(("without rating filter", no_rating_filters or None))

            no_genre_filters = dict(no_rating_filters)
            no_genre_filters.pop("genres", None)
            if no_genre_filters != no_rating_filters:
                filter_stages.append(("without genre filter", no_genre_filters or None))

        filter_stages.append(("no filters", None))

        all_results: list[tuple[Movie, float]] = []
        used_stage = ""
        stage_counts: list[tuple[str, int]] = []
        for stage_label, stage_filters in filter_stages:
            with console.status(f"[bold cyan]Searching ({stage_label})..."):
                stage_results: list[tuple[Movie, float]] = []
                for q in expanded_queries:
                    try:
                        results = engine.search(
                            query=q,
                            filters=stage_filters,
                            top_k=20,
                            ranking_strategy=engine_strategy,
                        )
                        for movie in results:
                            score = movie.search_score if movie.search_score is not None else 0.5
                            stage_results.append((movie, score))
                    except HybridSearchError:
                        continue

            stage_counts.append((stage_label, len(stage_results)))

            if stage_results:
                all_results = stage_results
                used_stage = stage_label
                break

        if debug_trace and stage_counts:
            trace_table = Table(title="Advanced Search Debug Trace", title_style="bold yellow")
            trace_table.add_column("Stage", style="bold")
            trace_table.add_column("Hits", justify="right")
            for label, count in stage_counts:
                trace_table.add_row(label, str(count))
            console.print(trace_table)

        if not all_results:
            console.print(
                "[bold yellow]No results found.[/] Try relaxing filters:\n"
                "  - Leave year empty\n"
                "  - Use rating range like 5 to 10\n"
                "  - Use broader genres like Action, Drama, Comedy"
            )
            return

        if used_stage and used_stage != "your exact filters":
            console.print(
                f"[bold yellow]No matches with strict filters.[/] Showing results {used_stage}."
            )

        with console.status("[bold cyan]Reranking results..."):
            reranker = SearchReranker()
            reranked = reranker.rerank(all_results, strategy=reranker_strategy)

        # Final intent alignment boost keeps query-relevant movies above broad semantic matches.
        query_tokens = {token for token in query.lower().split() if len(token) > 2}

        boosted_results: list[tuple[Movie, float]] = []
        for movie, score in reranked:
            overview_text = (movie.overview or "").lower()
            title_text = movie.title.lower()
            genre_set = {g.lower() for g in (movie.genres or [])}

            token_hits = sum(
                1
                for token in query_tokens
                if token in title_text or token in overview_text or token in genre_set
            )
            token_boost = min(0.20, 0.05 * token_hits)

            inferred_genre_boost = 0.0
            if inferred_genres and movie.genres:
                overlap = len({g.lower() for g in inferred_genres} & genre_set)
                inferred_genre_boost = min(0.20, 0.10 * overlap)

            boosted_score = min(1.0, score + token_boost + inferred_genre_boost)
            boosted_results.append((movie, boosted_score))

        boosted_results.sort(key=lambda pair: pair[1], reverse=True)

        deduplicated: list[Movie] = []
        seen_ids = set()
        for movie, _ in boosted_results:
            if movie.id not in seen_ids:
                deduplicated.append(movie)
                seen_ids.add(movie.id)
            if len(deduplicated) >= 15:
                break

        if not deduplicated:
            console.print("[bold yellow]No results after reranking.[/]\n")
            return

        _display_and_detail_results("Advanced Search Results", deduplicated)

    except (HybridSearchError, SearchRerankerError) as exc:
        console.print(f"[bold red]Search failed:[/] {exc}\n")


def _movie_recommendations(repo: MovieRepository, chroma: ChromaRepository) -> None:
    """Option 3: Recommend movies similar to a selected movie."""
    console.print(
        Panel(
            "[bold green]Movie Recommendations[/]\nPick a movie and find similar ones.",
            border_style="green",
        )
    )

    with console.status("[bold cyan]Loading top-rated movies..."):
        top_movies = repo.get_top_rated(limit=20)

    if not top_movies:
        console.print("[bold yellow]No movies available in database.[/]\n")
        return

    render_movie_table("Pick a movie for recommendations", top_movies[:10])
    choice_raw = console.input("[bold yellow]Enter movie number (1-10):[/] ").strip()
    try:
        choice_idx = int(choice_raw) - 1
        if not (0 <= choice_idx < len(top_movies)):
            console.print("[bold red]Invalid selection.[/]\n")
            return
    except ValueError:
        console.print("[bold red]Invalid input.[/]\n")
        return

    selected_movie = top_movies[choice_idx]
    console.print(f"\n[bold cyan]Finding movies similar to:[/] {selected_movie.title}")

    try:
        with console.status("[bold cyan]Generating embedding for selected movie..."):
            overview_text = f"{selected_movie.title}. {selected_movie.overview}"
            query_embedding = EmbeddingService().embed_text(overview_text)

        with console.status("[bold cyan]Searching for similar movies..."):
            similar_results = chroma.search(query_embedding=query_embedding, top_k=10)

        similar_movies: list[Movie] = []
        for result in similar_results:
            movie_id = result.get("id")
            if isinstance(movie_id, int) and movie_id != selected_movie.id:
                movie = repo.find_by_id(movie_id)
                if movie:
                    similar_movies.append(movie)

        if not similar_movies:
            console.print("[bold yellow]No similar movies found.[/]\n")
            return

        _display_and_detail_results(f"Movies Similar to '{selected_movie.title}'", similar_movies)

    except Exception as exc:
        console.print(f"[bold red]Recommendation failed:[/] {exc}\n")


def _smart_recommendations(repo: MovieRepository, chroma: ChromaRepository) -> None:
    """Option 4: Personalized recommendations based on user ratings."""
    console.print(
        Panel(
            "[bold yellow]Smart Recommendations[/]\nRate 5 random movies to get personalized suggestions.",
            border_style="yellow",
        )
    )

    with console.status("[bold cyan]Loading random movies..."):
        sample_movies = [repo.get_random_movie() for _ in range(5)]
        sample_movies = [m for m in sample_movies if m is not None]

    if len(sample_movies) < 3:
        console.print("[bold yellow]Not enough movies in database to generate recommendations.[/]\n")
        return

    console.print("\n[bold cyan]Rate these movies (1-10 or skip):[/]\n")
    ratings: dict[int, float] = {}
    for i, movie in enumerate(sample_movies, 1):
        render_movie_table(f"Movie {i}/{len(sample_movies)}", [movie])
        rating_raw = console.input("[bold yellow]Your rating (1-10) or skip [s]:[/] ").strip()
        if rating_raw.lower() != "s":
            try:
                rating = float(rating_raw)
                if 1 <= rating <= 10:
                    ratings[movie.id] = rating
            except ValueError:
                pass

    if not ratings:
        console.print("[bold yellow]No ratings provided.[/]\n")
        return

    avg_rating = sum(ratings.values()) / len(ratings)
    favorite_genres: set[str] = set()
    for movie_id in ratings:
        movie = repo.find_by_id(movie_id)
        if movie and movie.genres:
            favorite_genres.update(movie.genres)

    console.print(
        f"\n[bold cyan]Your preferences:[/] avg_rating={avg_rating:.1f}, "
        f"favorite_genres={', '.join(sorted(favorite_genres)[:5])}"
    )

    reranker = SearchReranker()
    try:
        with console.status("[bold cyan]Finding movies matching your preferences..."):
            all_movies = repo.find_all(limit=100)
            scored: list[tuple[Movie, float]] = []

            for movie in all_movies:
                if movie.id in ratings:
                    continue

                score = 0.0
                if movie.vote_average and movie.vote_average >= avg_rating - 1:
                    score += 0.5

                if movie.genres:
                    genre_overlap = len(set(movie.genres) & favorite_genres)
                    score += 0.3 * min(genre_overlap / 3, 1.0)

                if score > 0:
                    scored.append((movie, score))

            scored.sort(key=lambda x: x[1], reverse=True)

        if not scored:
            console.print("[bold yellow]No matching recommendations found.[/]\n")
            return

        preferences = {"favorite_genres": list(favorite_genres), "min_rating": max(5.0, avg_rating - 2)}
        reranked = reranker.rerank(scored[:30], strategy="personalized", user_preferences=preferences)

        results = [movie for movie, _ in reranked[:10]]
        _display_and_detail_results("Personalized Recommendations", results)

    except Exception as exc:
        console.print(f"[bold red]Recommendation generation failed:[/] {exc}\n")


def _compare_search_methods(repo: MovieRepository) -> None:
    """Option 5: Compare semantic vs keyword search."""
    console.print(
        Panel(
            "[bold cyan]Compare Search Methods[/]\nSee how semantic vs keyword search differ.",
            border_style="cyan",
        )
    )

    query = console.input("[bold yellow]Enter query for comparison:[/] ").strip()
    if not query:
        console.print("[bold red]Query cannot be empty.[/]\n")
        return

    try:
        with console.status("[bold cyan]Running keyword search..."):
            keyword_results = repo.find_by_keywords(query, limit=10)

        with console.status("[bold cyan]Running semantic search..."):
            chroma = _ensure_embeddings_available()
            semantic_results = []
            if chroma:
                try:
                    embedding = EmbeddingService().embed_text(query)
                    semantic_data = chroma.search(query_embedding=embedding, top_k=10)
                    for result in semantic_data:
                        movie_id = result.get("id")
                        if isinstance(movie_id, int):
                            movie = repo.find_by_id(movie_id)
                            if movie:
                                semantic_results.append(movie)
                except ChromaRepositoryError:
                    pass

        keyword_table = Table(title="Keyword Search Results", title_style="magenta")
        keyword_table.add_column("No", style="dim")
        keyword_table.add_column("Title", style="bold")
        keyword_table.add_column("Year")
        for idx, m in enumerate(keyword_results, 1):
            year = m.release_date.split("-")[0] if m.release_date else "-"
            keyword_table.add_row(str(idx), m.title, year)
        console.print(keyword_table)

        if semantic_results:
            semantic_table = Table(title="Semantic Search Results", title_style="cyan")
            semantic_table.add_column("No", style="dim")
            semantic_table.add_column("Title", style="bold")
            semantic_table.add_column("Year")
            for idx, m in enumerate(semantic_results, 1):
                year = m.release_date.split("-")[0] if m.release_date else "-"
                semantic_table.add_row(str(idx), m.title, year)
            console.print(semantic_table)

            keyword_titles = {m.title for m in keyword_results}
            semantic_titles = {m.title for m in semantic_results}
            semantic_only = sorted(semantic_titles - keyword_titles)

            if semantic_only:
                console.print(
                    f"\n[bold green]Semantic-only matches:[/] {', '.join(semantic_only[:3])}..."
                )
        else:
            console.print("[bold yellow]Semantic search unavailable (no embeddings).[/]")

        console.print(
            "\n[bold cyan]Key Difference:[/] Keyword search finds exact word matches. "
            "Semantic search understands meaning, so it can find thematically related movies "
            "even when words don't overlap exactly.\n"
        )

    except Exception as exc:
        console.print(f"[bold red]Comparison failed:[/] {exc}\n")


def _display_and_detail_results(title: str, movies: list[Movie]) -> None:
    """Display results table and optionally show details for a selected movie."""
    if not movies:
        return

    render_movie_table(title, movies[:15])

    while True:
        choice_raw = console.input(
            f"[bold yellow]View details (1-{len(movies)}) or press Enter to return:[/] "
        ).strip()
        if not choice_raw:
            return
        try:
            idx = int(choice_raw) - 1
            if 0 <= idx < len(movies):
                display_movie_details(movies[idx])
                console.input("Press Enter to continue...")
            else:
                console.print("[bold red]Out of range.[/]")
        except ValueError:
            console.print("[bold red]Invalid input.[/]")


def _show_main_menu(repo: MovieRepository) -> str:
    """Render and return the user's menu choice."""
    menu = Panel(
        "[bold cyan]🎬 MovieSearch Pro[/]\n"
        "[dim]Semantic search, filtering, and recommendations[/]\n\n"
        "[bold green]1.[/] Simple Search (semantic-only)\n"
        "[bold green]2.[/] Advanced Search (filters + expansion + reranking)\n"
        "[bold green]3.[/] Movie Recommendations (pick one, find similar)\n"
        "[bold green]4.[/] Smart Recommendations (personalized)\n"
        "[bold green]5.[/] Compare Search Methods (semantic vs keyword)\n"
        "[bold green]6.[/] Exit",
        title="Main Menu",
        border_style="bold cyan",
    )
    console.print(menu)
    return console.input("[bold yellow]Choose an option (1-6):[/] ").strip()


def _run_interactive_menu() -> None:
    """Main interactive menu loop."""
    initialize_database()
    repo = MovieRepository()

    try:
        movie_count = repo.count()
    except RepositoryError:
        movie_count = 0

    if movie_count == 0:
        console.print("[bold yellow]Your database is empty.[/] Let's import some movies.\n")
        run_import_flow()
        return

    engine = HybridSearchEngine(
           ChromaRepository(), 
           repo, 
           EmbeddingService(),  # Updated to use EmbeddingService
    )
    expander = QueryExpander()
    chroma = _ensure_embeddings_available()

    while True:
        choice = _show_main_menu(repo)

        if choice == "1":
            _simple_search(repo, engine)
        elif choice == "2":
            _advanced_search(repo, engine, expander)
        elif choice == "3":
            if not chroma:
                console.print("[bold red]Embeddings required for recommendations.[/]\n")
            else:
                _movie_recommendations(repo, chroma)
        elif choice == "4":
            if not chroma:
                console.print("[bold red]Embeddings required for smart recommendations.[/]\n")
            else:
                _smart_recommendations(repo, chroma)
        elif choice == "5":
            _compare_search_methods(repo)
        elif choice == "6":
            console.print("[bold cyan]Thanks for using MovieSearch Pro! Goodbye! 🎬[/]\n")
            return
        else:
            console.print("[bold red]Invalid choice. Please select 1-6.[/]\n")


def main() -> None:
    """CLI entrypoint with support for import and interactive modes.

    Usage:
        python main.py              # Default: interactive menu
        python main.py --import     # Force import, then menu
        python main.py --interactive  # Interactive menu (legacy flag)
    """
    try:
        settings = get_settings()
    except ValidationError as exc:
        console.print(f"[bold red]Configuration error:[/]\n{exc}")
        sys.exit(1)

    if settings.debug:
        logging.basicConfig(level=logging.DEBUG)

    args = set(sys.argv[1:])

    if "--import" in args:
        run_import_flow()
        go_interactive = console.input("Start interactive search? [y/N]: ").strip().lower()
        if go_interactive in {"y", "yes"}:
            _run_interactive_menu()
        return

    _run_interactive_menu()


if __name__ == "__main__":
    main()
