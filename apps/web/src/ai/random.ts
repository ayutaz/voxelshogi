// Easy AI: uniformly random legal move. The engine supplies the legal moves.
export type Rng = () => number;

/** Mulberry32: small deterministic PRNG returning floats in [0, 1). */
export function createRng(seed: number): Rng {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function pickRandomMove(legal: readonly string[], rng: Rng): string | null {
  if (legal.length === 0) return null;
  return legal[Math.floor(rng() * legal.length)] ?? null;
}
