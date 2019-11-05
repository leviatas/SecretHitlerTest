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

CREATE TABLE IF NOT EXISTS stats (
    id bigint PRIMARY KEY,
    fascistwinhitler INTEGER NOT NULL,
    fascistwinpolicies INTEGER NOT NULL,
    liberalwinpolicies INTEGER NOT NULL,
    liberalwinkillhitler INTEGER NOT NULL,
    cancelgame INTEGER NOT NULL
);

--DROP TABLE IF EXISTS stats_detail;

CREATE TABLE IF NOT EXISTS stats_detail (
    id SERIAL PRIMARY KEY,
    playerlist TEXT,
    game_endcode INTEGER NOT NULL,
    liberal_track INTEGER NOT NULL,
    fascist_track INTEGER NOT NULL,
    num_players INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS config (
     id bigint PRIMARY KEY,
     token TEXT NOT NULL
 );

CREATE TABLE IF NOT EXISTS user_stats (
    id SERIAL PRIMARY KEY,
    data text NOT NULL
); 

CREATE TABLE IF NOT EXISTS achivements (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description text NOT NULL
);

-- If there are no stats in the stats table I initiate it.
DO $$
BEGIN 
  IF (SELECT count(*) = 0 FROM stats) THEN
   INSERT INTO stats VALUES (1, 0, 0, 0, 0, 0);
  END IF; 
END $$;
--
