-- SQLite schema for movie storage.
-- TMDB movie IDs are used as the primary key (no AUTOINCREMENT).

CREATE TABLE IF NOT EXISTS movies (
  id INTEGER PRIMARY KEY,
  title TEXT NOT NULL,
  release_date TEXT, -- ISO format YYYY-MM-DD
  overview TEXT,
  vote_average REAL CHECK (vote_average >= 0 AND vote_average <= 10),
  vote_count INTEGER,
  genres TEXT, -- JSON array stored as text
  poster_path TEXT,
  runtime INTEGER,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (id)
);

CREATE INDEX IF NOT EXISTS idx_movies_title ON movies(title);
CREATE INDEX IF NOT EXISTS idx_movies_release_date ON movies(release_date);
CREATE INDEX IF NOT EXISTS idx_movies_vote_average ON movies(vote_average);

