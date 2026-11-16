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
  sleep?: (ms: number) => Promise<void>;
  onCall?: (done: number) => void;
}): Sleeper {
  const cap = opts.concurrency ?? 8;
  const attempts = opts.retries ?? 4;
  const sleep = opts.sleep ?? defaultSleep;
  let inFlight = 0;
  let done = 0;
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

  const api: Sleeper = {
    calls: 0,
    async text(path) {
      await acquire();
      try {
        for (let attempt = 1; attempt <= attempts; attempt++) {
          let wait: number;
          try {
            api.calls++;
            const res = await opts.fetch(`${SLEEPER_BASE}/${path}`);
            opts.onCall?.(++done);
            if (res.status === 200) return await res.text();
            if (res.status === 404) return null;
            wait = res.status === 429 ? 5000 * attempt : 1000 * attempt;
          } catch {
            wait = 1000 * attempt;
          }
          if (attempt < attempts) await sleep(wait);
        }
        throw new SleeperError();
      } finally {
        release();
      }
    },
  };
  return api;
}
