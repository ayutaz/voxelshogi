import type { AutomaticSubmission } from './automatic-contract';
import type { GameDatabase } from './receiver';

interface Stored { version: number; payload_sha256: string; status: string }
export async function persistAutomatic(db: GameDatabase, value: AutomaticSubmission, body: string, sha: string, bytes: number) {
  const changed = await db.prepare(`INSERT INTO automatic_games(game_id, version, request_id, payload_sha256, payload, payload_bytes, state, progress_writes)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(game_id) DO UPDATE SET
      version = excluded.version, request_id = excluded.request_id, payload_sha256 = excluded.payload_sha256,
      payload = excluded.payload, payload_bytes = excluded.payload_bytes, state = excluded.state,
      progress_writes = automatic_games.progress_writes + CASE WHEN excluded.state = 'progress' THEN 1 ELSE 0 END,
      status = 'received_unverified', updated_at = unixepoch()
    WHERE excluded.version > automatic_games.version`)
    .bind(value.gameId, value.version, value.requestId, sha, body, bytes, value.state, value.state === 'progress' ? 1 : 0).run();
  if (!changed.success) throw new Error('write failed');
  const row = await db.prepare('SELECT version, payload_sha256, status FROM automatic_games WHERE game_id = ?')
    .bind(value.gameId).first<Stored>();
  if (!row) throw new Error('read failed');
  if (row.version === value.version && row.payload_sha256 !== sha) throw new Error('collection_conflict');
  return { body: { gameId: value.gameId, requestId: value.requestId, version: row.version, status: row.status,
    duplicate: changed.meta.changes === 0 && row.version === value.version, ignored: row.version > value.version },
  status: changed.meta.changes === 1 && value.version === 1 ? 201 : 200 };
}
