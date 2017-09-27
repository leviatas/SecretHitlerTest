CREATE TABLE IF NOT EXISTS users2 (
    id SERIAL PRIMARY KEY,
    facebook_id TEXT NOT NULL,
    name TEXT NOT NULL,
    access_token TEXT,
    created INTEGER NOT NULL
);
