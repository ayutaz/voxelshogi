import { createPolicyRuntime } from './policy-factory';
import { PolicyWorkerHost } from './policy-host';

const host = new PolicyWorkerHost(createPolicyRuntime, progress => self.postMessage(progress));
self.onmessage = (event: MessageEvent<unknown>) => {
  // Dedicated Worker messages have an empty origin; this is not a Window endpoint.
  if (event.origin !== '') return;
  void host.run(event.data).then(reply => self.postMessage(reply));
};
