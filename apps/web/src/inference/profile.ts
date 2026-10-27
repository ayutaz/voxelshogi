/** ORT 1.31.1 native profile: placement only; durations aren't GPU execution time. */
export function profileNode(line: string): { provider: string; operator: string } | null {
  const text = line.trim().replace(/,$/, '');
  if (!text.startsWith('{')) return null;
  try {
    const event = JSON.parse(text) as { cat?: unknown; args?: { provider?: unknown; op_name?: unknown } };
    if (event.cat === 'Node' && typeof event.args?.provider === 'string' && typeof event.args.op_name === 'string') return { provider: event.args.provider, operator: event.args.op_name };
  } catch { /* ordinary log lines are not profile evidence */ }
  return null;
}
