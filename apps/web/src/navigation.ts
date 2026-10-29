export type Screen = 'arena' | 'models';
export function screenForQuery(search: string): Screen {
  const query = new URLSearchParams(search);
  if (query.has('models')) return 'models';
  return 'arena';
}
export const ARENA_LINKS = [{ href: '/?models=1', label: 'モデル推論ラボ' }];
export const MODEL_LINKS = [{ href: '/', label: 'AI対局の観戦へ' }];
