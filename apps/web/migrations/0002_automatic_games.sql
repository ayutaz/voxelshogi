-- Separate from v1: automatic snapshots never assert the legacy opt-in consent.
CREATE TABLE automatic_games (
  game_id TEXT PRIMARY KEY,
  version INTEGER NOT NULL CHECK(version >= 1),
  request_id TEXT NOT NULL,
  payload_sha256 TEXT NOT NULL CHECK(length(payload_sha256) = 64),
  payload TEXT NOT NULL CHECK(json_valid(payload)),
  payload_bytes INTEGER NOT NULL CHECK(payload_bytes > 0 AND payload_bytes <= 262144 AND payload_bytes = length(CAST(payload AS BLOB))),
  state TEXT NOT NULL CHECK(state IN ('progress', 'finished', 'aborted')),
  progress_writes INTEGER NOT NULL CHECK(progress_writes BETWEEN 0 AND 128),
  status TEXT NOT NULL DEFAULT 'received_unverified' CHECK(status IN ('received_unverified', 'verified', 'rejected')),
  created_at INTEGER NOT NULL DEFAULT (unixepoch()),
  updated_at INTEGER NOT NULL DEFAULT (unixepoch())
);
CREATE INDEX automatic_created_at ON automatic_games(created_at);
CREATE TABLE automatic_usage (
  singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
  day TEXT NOT NULL DEFAULT (date('now')),
  daily_updates INTEGER NOT NULL DEFAULT 0 CHECK(daily_updates >= 0)
);
INSERT INTO automatic_usage(singleton) VALUES (1);

CREATE TRIGGER automatic_insert_guard BEFORE INSERT ON automatic_games
WHEN NOT EXISTS (SELECT 1 FROM automatic_games WHERE game_id = NEW.game_id)
BEGIN
  SELECT CASE WHEN EXISTS (
    SELECT 1 FROM collection_usage WHERE singleton = 1 AND
      ((day = date('now') AND daily_count >= 1000) OR retained_bytes + NEW.payload_bytes > 104857600)
  ) OR EXISTS (
    SELECT 1 FROM automatic_usage WHERE singleton = 1 AND day = date('now') AND daily_updates >= 10000
  ) THEN RAISE(ABORT, 'collection_quota') END;
END;

CREATE TRIGGER automatic_update_guard BEFORE UPDATE OF payload ON automatic_games
BEGIN
  SELECT CASE WHEN OLD.state != 'progress'
    OR NEW.version <= OLD.version
    OR json_extract(NEW.payload, '$.applicationCommit') != json_extract(OLD.payload, '$.applicationCommit')
    OR json_extract(NEW.payload, '$.mode') != json_extract(OLD.payload, '$.mode')
    OR json_extract(NEW.payload, '$.selectedAgents') != json_extract(OLD.payload, '$.selectedAgents')
    OR json_extract(NEW.payload, '$.record.initial') != json_extract(OLD.payload, '$.record.initial')
    OR json_array_length(NEW.payload, '$.record.moves') < json_array_length(OLD.payload, '$.record.moves')
    OR EXISTS (
      SELECT 1 FROM json_each(OLD.payload, '$.record.moves') m
      WHERE m.value != json_extract(NEW.payload, '$.record.moves[' || m.key || ']')
    ) THEN RAISE(ABORT, 'collection_conflict') END;
  SELECT CASE WHEN (NEW.state = 'progress' AND OLD.progress_writes >= 128)
    OR EXISTS (SELECT 1 FROM collection_usage WHERE singleton = 1 AND retained_bytes + NEW.payload_bytes - OLD.payload_bytes > 104857600)
    OR EXISTS (SELECT 1 FROM automatic_usage WHERE singleton = 1 AND day = date('now') AND daily_updates >= 10000)
    THEN RAISE(ABORT, 'collection_quota') END;
END;

CREATE TRIGGER automatic_account_insert AFTER INSERT ON automatic_games
BEGIN
  UPDATE collection_usage SET
    daily_count = CASE WHEN day = date('now') THEN daily_count + 1 ELSE 1 END,
    day = date('now'), retained_bytes = retained_bytes + NEW.payload_bytes WHERE singleton = 1;
  UPDATE automatic_usage SET
    daily_updates = CASE WHEN day = date('now') THEN daily_updates + 1 ELSE 1 END,
    day = date('now') WHERE singleton = 1;
END;
CREATE TRIGGER automatic_account_update AFTER UPDATE OF payload ON automatic_games
BEGIN
  UPDATE collection_usage SET retained_bytes = retained_bytes + NEW.payload_bytes - OLD.payload_bytes WHERE singleton = 1;
  UPDATE automatic_usage SET
    daily_updates = CASE WHEN day = date('now') THEN daily_updates + 1 ELSE 1 END,
    day = date('now') WHERE singleton = 1;
END;
CREATE TRIGGER automatic_account_delete AFTER DELETE ON automatic_games
BEGIN
  UPDATE collection_usage SET retained_bytes = retained_bytes - OLD.payload_bytes WHERE singleton = 1;
END;
