// Sleeper's API client: returns each response's exact text, retries politely, caps requests in flight.
export type Fetch = typeof fetch;
export const SLEEPER_BASE = "https://api.sleeper.app/v1";

export class SleeperError extends Error {
  constructor(message = "Sleeper is not responding") {
    super(message);
    this.name = "SleeperError";
  }
}

export interface Sleeper {
  /** Requests sent so far. */
  calls: number;
  /** The body text of GET SLEEPER_BASE/path; null when Sleeper says 404. */
  text(path: string): Promise<string | null>;
}

const defaultSleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

export function createSleeper(opts: {
  fetch: Fetch;
  concurrency?: number;
  retries?: number;
  timeoutMs?: number;
  sleep?: (ms: number) => Promise<void>;
  onCall?: (done: number) => void;
}): Sleeper {
  const cap = opts.concurrency ?? 8;
  const attempts = opts.retries ?? 4;
  const timeoutMs = opts.timeoutMs ?? 30000;
  const sleep = opts.sleep ?? defaultSleep;
  let inFlight = 0;
  let finished = 0;
  const waiting: Array<() => void> = [];

  const acquire = async () => {
    if (inFlight < cap) {
      inFlight++;
      return;
    }
    // The releasing request hands its slot straight to us, so inFlight stays put.
    await new Promise<void>((resolve) => waiting.push(resolve));
  };
  const release = () => {
    const next = waiting.shift();
    if (next) next();
    else inFlight--;
  };

  /** One request, aborted if it (or reading its body) takes longer than timeoutMs. */
  const attempt = async (path: string): Promise<{ status: number; body: string }> => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      api.calls++;
      const res = await opts.fetch(`${SLEEPER_BASE}/${path}`, { signal: controller.signal });
      return { status: res.status, body: res.status === 200 ? await res.text() : "" };
    } finally {
      clearTimeout(timer);
      opts.onCall?.(++finished);
    }
  };

  const api: Sleeper = {
    calls: 0,
    async text(path) {
      await acquire();
      try {
        for (let n = 1; n <= attempts; n++) {
          let wait = 1000 * n;
          try {
            const { status, body } = await attempt(path);
            if (status === 200 && body !== "") return body;
            if (status === 404) return null;
            if (status === 429) wait = 5000 * n;
            else if (status >= 400 && status < 500) throw new SleeperError(`Sleeper answered ${status}`);
          } catch (error) {
            if (error instanceof SleeperError) throw error;
          }
          if (n < attempts) await sleep(wait);
        }
        throw new SleeperError();
      } finally {
        release();
      }
    },
  };
  return api;
}
