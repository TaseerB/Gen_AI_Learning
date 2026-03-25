"""Run movie-search importer as a module: `python -m movie_search`."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_app_main():
    root = Path(__file__).resolve().parents[1]
    app_dir = root / "movie-search"

    # Ensure app-local imports (config, models, repositories, services) resolve.
    if str(app_dir) not in sys.path:
        sys.path.insert(0, str(app_dir))

    module_path = app_dir / "main.py"
    spec = importlib.util.spec_from_file_location("movie_search_app_main", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {module_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    app = _load_app_main()
    app.main()

