import { handle } from "./protocol";

self.addEventListener("message", (e: MessageEvent) => {
  self.postMessage(handle(e.data));
});
