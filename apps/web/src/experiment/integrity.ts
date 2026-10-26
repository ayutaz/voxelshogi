/** Detects byte drift between the measured sample and the displayed record. */
export async function verifyDigest(text: string, expected: string): Promise<void> {
  const bytes = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  const actual = Array.from(new Uint8Array(bytes), (b) => b.toString(16).padStart(2, '0')).join('');
  if (!/^[a-f0-9]{64}$/.test(expected) || actual !== expected) throw new Error('棋譜のSHA-256が一致しません');
}
