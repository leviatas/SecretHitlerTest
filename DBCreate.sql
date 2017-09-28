--drop table if exists users;
--drop table if exists games;

CREATE TABLE IF NOT EXISTS users (
    uid bigint PRIMARY KEY,
    name text NOT NULL
);

CREATE TABLE IF NOT EXISTS games (
    cid bigint PRIMARY KEY,
    groupName TEXT NOT NULL,
    data json NOT NULL
);

