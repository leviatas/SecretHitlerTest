CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    facebook_id TEXT NOT NULL,
    name TEXT NOT NULL,
    access_token TEXT,
    created INTEGER NOT NULL
);
