"""Movie Search Application – entry point."""

from pydantic import ValidationError

from config.settings import get_settings


def main() -> None:
    """Bootstrap the application and verify configuration."""
    try:
        settings = get_settings()
    except ValidationError as exc:
        print(f"Configuration error:\n{exc}")
        raise SystemExit(1)

    if settings.debug:
        print(f"Base URL : {settings.tmdb_base_url}")
        print("API Key  : ****" + settings.tmdb_api_key[-4:])

    print("Movie Search application started successfully.")


if __name__ == "__main__":
    main()
