import type { Page } from '@playwright/test';

export interface InteractionEvent {
  kind: string;
  at: number;
  pending: boolean;
  phase: string;
  trusted?: boolean;
  buttons?: number;
  worker?: number;
  requestId?: number;
  metrics?: unknown;
}
interface Probe {
  events: InteractionEvent[];
  frames: number;
  camera?: InteractionEvent;
  armCamera: () => void;
}
declare global { interface Window { interactionProbe: Probe } }

/** Observes real browser events and real Worker traffic without delaying replies. */
export async function installInteractionProbe(page: Page) {
  await page.addInitScript(() => {
    const probe: Probe = window.interactionProbe = { events: [] as InteractionEvent[], frames: 0, armCamera };
    const active = new Set<number>();
    const mark = (kind: string, detail: Partial<InteractionEvent> = {}) => {
      const event = { kind, at: performance.now(), pending: active.size > 0,
        phase: document.querySelector('[data-testid="ai-phase"]')?.textContent ?? '', ...detail };
      probe.events.push(event);
      return event;
    };
    function armCamera() {
      const finish = (event: PointerEvent) => {
        if (!(event.target instanceof HTMLCanvasElement)) return;
        window.removeEventListener('pointerup', finish);
        probe.camera = mark('camera-end', { trusted: event.isTrusted, buttons: event.buttons });
        // Sample at the actual input event, before the driver's next RPC.
        // Never hold, replace, or delay the real search result.
        if (probe.camera.pending && probe.camera.phase.includes('思考中')) {
          document.querySelector<HTMLButtonElement>('[data-testid="cancel-search"]')?.click();
        }
      };
      window.addEventListener('pointerup', finish);
    }
    const NativeWorker = window.Worker;
    let nextWorker = 0;
    window.Worker = class extends NativeWorker {
      private id = ++nextWorker;
      constructor(url: string | URL, options?: WorkerOptions) {
        super(url, options);
        this.addEventListener('message', ({ data }) => {
          active.delete(this.id);
          mark('reply', { worker: this.id, requestId: data.requestId, metrics: data.metrics });
        });
      }
      override postMessage(message: { requestId: number }, transferOrOptions?: Transferable[] | StructuredSerializeOptions) {
        active.add(this.id);
        mark('request', { worker: this.id, requestId: message.requestId });
        if (Array.isArray(transferOrOptions)) super.postMessage(message, transferOrOptions);
        else super.postMessage(message, transferOrOptions);
      }
      override terminate() {
        mark('terminate', { worker: this.id });
        active.delete(this.id);
        super.terminate();
      }
    };
    for (const kind of ['pointerdown', 'pointermove', 'pointerup'] as const) {
      window.addEventListener(kind, (event) => {
        if (event.target instanceof HTMLCanvasElement) mark(kind, { trusted: event.isTrusted, buttons: event.buttons });
      }, true);
    }
    document.addEventListener('click', (event) => {
      if ((event.target as HTMLElement)?.dataset.testid === 'cancel-search') mark('cancel');
    }, true);
    const clear = WebGL2RenderingContext.prototype.clear;
    WebGL2RenderingContext.prototype.clear = function (mask) {
      probe.frames++;
      return clear.call(this, mask);
    };
    let drawnFrame = -1;
    const draw = WebGL2RenderingContext.prototype.drawElementsInstanced;
    WebGL2RenderingContext.prototype.drawElementsInstanced = function (mode, count, type, offset, instances) {
      draw.call(this, mode, count, type, offset, instances);
      if (count > 0 && instances > 0 && drawnFrame !== probe.frames) {
        drawnFrame = probe.frames;
        mark('draw');
      }
    };
  });
}

export async function readInteractionProbe(page: Page) {
  return page.evaluate(() => {
    const { events, frames, camera } = window.interactionProbe;
    const gl = document.querySelector('canvas')?.getContext('webgl2');
    const debug = gl?.getExtension('WEBGL_debug_renderer_info');
    return { events, frames, camera, observedAt: performance.now(), timeOrigin: performance.timeOrigin,
      userAgent: navigator.userAgent, renderer: gl && debug ? gl.getParameter(debug.UNMASKED_RENDERER_WEBGL) : null };
  });
}
