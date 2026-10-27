export interface AssetTiming { url: string; startMs: number; durationMs: number; transferBytes: number; encodedBytes: number; decodedBytes: number; protocol: string; delivery: string }
interface ResourceEntry { entryType: string; name: string; startTime: number; duration: number; transferSize: number; encodedBodySize: number; decodedBodySize: number; nextHopProtocol: string; deliveryType?: string }

export function resourceTimings(entries: readonly ResourceEntry[], origin: string, since: number): AssetTiming[] {
  const prefix = new URL('/models/m3/', origin).href;
  return entries.filter(e => e.entryType === 'resource' && e.startTime >= since && e.name.startsWith(prefix)).map(e => ({
    url: e.name, startMs: e.startTime, durationMs: e.duration, transferBytes: e.transferSize, encodedBytes: e.encodedBodySize,
    decodedBytes: e.decodedBodySize, protocol: e.nextHopProtocol, delivery: e.deliveryType ?? '',
  }));
}

export function collectResourceTimings(since: number): AssetTiming[] {
  if (typeof location === 'undefined') return [];
  return resourceTimings(performance.getEntriesByType('resource') as PerformanceResourceTiming[], location.origin, since);
}
