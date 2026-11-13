CREATE TABLE games (
  request_id TEXT PRIMARY KEY,
  payload_sha256 TEXT NOT NULL CHECK(length(payload_sha256) = 64),
  payload TEXT NOT NULL CHECK(json_valid(payload)),
  payload_bytes INTEGER NOT NULL CHECK(payload_bytes > 0 AND payload_bytes <= 262144 AND payload_bytes = length(CAST(payload AS BLOB))),
  status TEXT NOT NULL DEFAULT 'received_unverified' CHECK(status IN ('received_unverified', 'verified', 'rejected')),
  created_at INTEGER NOT NULL DEFAULT (unixepoch())
);
CREATE INDEX games_created_at ON games(created_at);

CREATE TABLE collection_usage (
  singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
  day TEXT NOT NULL DEFAULT (date('now')),
  daily_count INTEGER NOT NULL DEFAULT 0 CHECK(daily_count >= 0),
  retained_bytes INTEGER NOT NULL DEFAULT 0 CHECK(retained_bytes >= 0)
);
INSERT INTO collection_usage(singleton) VALUES (1);

-- Triggers run in the same transaction as the insert, including concurrent requests.
-- Existing IDs do not consume quota again (the receiver checks their SHA separately).
CREATE TRIGGER games_quota BEFORE INSERT ON games
WHEN NOT EXISTS (SELECT 1 FROM games WHERE request_id = NEW.request_id)
BEGIN
  SELECT CASE WHEN EXISTS (
    SELECT 1 FROM collection_usage WHERE singleton = 1 AND
      ((day = date('now') AND daily_count >= 1000) OR retained_bytes + NEW.payload_bytes > 104857600)
  ) THEN RAISE(ABORT, 'collection_quota') END;
END;
CREATE TRIGGER games_account_insert AFTER INSERT ON games
BEGIN
  UPDATE collection_usage SET
    daily_count = CASE WHEN day = date('now') THEN daily_count + 1 ELSE 1 END,
    day = date('now'), retained_bytes = retained_bytes + NEW.payload_bytes WHERE singleton = 1;
END;
CREATE TRIGGER games_account_delete AFTER DELETE ON games
BEGIN
  UPDATE collection_usage SET retained_bytes = retained_bytes - OLD.payload_bytes WHERE singleton = 1;
END;
