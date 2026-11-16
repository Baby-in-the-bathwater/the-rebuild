import { handle } from "./protocol";

declare const self: DedicatedWorkerGlobalScope;

self.addEventListener("message", (e: MessageEvent) => {
  self.postMessage(handle(e.data));
});
