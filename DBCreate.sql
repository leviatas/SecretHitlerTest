--DROP TABLE IF EXISTS users;
--DROP TABLE IF EXISTS games;


CREATE TABLE IF NOT EXISTS users (
    id bigint PRIMARY KEY,
    name text NOT NULL
);

CREATE TABLE IF NOT EXISTS games (
    id bigint PRIMARY KEY,
    groupName TEXT NOT NULL,
    data text NOT NULL
);
