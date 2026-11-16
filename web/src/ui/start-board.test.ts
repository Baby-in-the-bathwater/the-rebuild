// @vitest-environment jsdom
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { EngineRequest, EngineResponse } from "../engine/protocol";
import { TRADE_HISTORY_NOTICE } from "../report/run";
import { NO_BENCHMARK_NOTICE, startBoard, type BoardSources, type BoardWorker } from "./board";
import { webRoot } from "../testing/fixture";

/** A worker that records each request and answers it with `reply` (after a tick, as a real worker would). */
function stubWorker(reply: (req: EngineRequest) => Omit<EngineResponse, "id">) {
  const listeners: ((e: { data: unknown }) => void)[] = [];
  const posted: EngineRequest[] = [];
  const worker: BoardWorker & { posted: EngineRequest[]; terminated: boolean } = {
    posted,
    terminated: false,
    postMessage(msg) {
      const req = msg as EngineRequest;
      posted.push(req);
      setTimeout(() => listeners.forEach((l) => l({ data: { ...reply(req), id: req.id } })), 0);
    },
    addEventListener(type, listener) {
      if (type === "message") listeners.push(listener);
    },
    terminate() {
      worker.terminated = true;
    },
  };
  return worker;
}

const failing = (message: string) => stubWorker(() => ({ type: "error", message, kind: "league" }) as const);
const benchmark = { label: "12-team superflex", team_seasons: 120, built: "2026-01-01" };
const succeeding = (summary: Record<string, unknown>, notices: string[] = []) =>
  stubWorker(() => ({
    type: "report",
    report: { league_id: "42", roster_id: 3, summary, board_data: { league: "Synthetic" }, brief: "", notices },
  }));
/** The board's markup without its scripts: the board itself is tested in board.test.ts. */
const sources: BoardSources = { css: "", body: '<div id="rosters"></div>', weightsJs: "", boardJs: "" };
const noticesShown = () => [...document.querySelectorAll(".site-notice")].map((n) => n.textContent);
const boardShown = () => vi.waitFor(() => expect(document.getElementById("rosters")).not.toBeNull());

function open(path: string) {
  window.history.replaceState(null, "", path);
  document.body.className = "site-page";
  document.body.innerHTML = '<main id="site-main"><h1>Building the trade board</h1></main>';
}

const main = () => document.getElementById("site-main")!;
const errorShown = () => vi.waitFor(() => expect(document.querySelector(".site-message")).not.toBeNull());

describe("startBoard", () => {
  beforeEach(() => vi.restoreAllMocks());

  it.each([
    ["/board", "no parameters"],
    ["/board?team=Team+3", "no league"],
    ["/board?league=42", "no team"],
    ["/board?league=L1&team=Team+3", "a league id that is not all digits"],
    ["/board?league=42abc&team=Team+3", "a league id with letters"],
  ])("links back to the form for %s (%s), without starting the engine", (path) => {
    open(path);
    const create = vi.fn(() => failing("unused"));
    startBoard(document, window, create);
    const link = main().querySelector<HTMLAnchorElement>("a")!;
    expect(link.getAttribute("href")).toBe("/");
    expect(link.textContent).toBe("Open the form");
    expect(create).not.toHaveBeenCalled();
  });

  it("asks for a fresh report with fresh=1 and removes it from the address", async () => {
    open("/board?league=42&team=Team+3&fresh=1");
    const replace = vi.spyOn(window.history, "replaceState");
    const worker = failing("no");
    startBoard(document, window, () => worker);
    expect(replace).toHaveBeenCalledTimes(1);
    expect(window.location.search).toBe("?league=42&team=Team+3");
    await errorShown();
    expect(worker.posted).toEqual([{ id: 1, type: "report", leagueId: "42", team: "Team 3", fresh: true }]);
  });

  it("does not ask for a fresh report without fresh=1", async () => {
    open("/board?league=42&team=Team+3");
    const replace = vi.spyOn(window.history, "replaceState");
    const worker = failing("no");
    startBoard(document, window, () => worker);
    await errorShown();
    expect(replace).not.toHaveBeenCalled();
    expect(worker.posted).toEqual([{ id: 1, type: "report", leagueId: "42", team: "Team 3" }]);
    expect(worker.terminated).toBe(true);
  });

  it("shows a multi-line error with its line breaks kept", async () => {
    open("/board?league=42&team=Nobody");
    const text = "No team matches \"Nobody\".\nTeams in this league:\n  Team 1\n  Team 2";
    startBoard(document, window, () => failing(text));
    await errorShown();
    const message = document.querySelector<HTMLElement>(".site-message")!;
    expect(message.classList.contains("site-message")).toBe(true);
    expect(message.textContent).toBe(text);
    expect(message.textContent).toContain("\n");
    // the class is what keeps the newlines visible
    const siteCss = readFileSync(join(webRoot, "src", "ui", "site.css"), "utf8"); // Vitest serves CSS imports empty
    expect(siteCss).toMatch(/\.site-message\s*\{[^}]*white-space:\s*pre-line/);
  });

  it("makes Try again repeat a fresh run as a fresh run", async () => {
    open("/board?league=42&team=Team+3&fresh=1");
    startBoard(document, window, () => failing("Sleeper is not responding."));
    await errorShown();
    const again = [...main().querySelectorAll("a")].find((a) => a.textContent === "Try again")!;
    expect(again.getAttribute("href")).toBe("/board?league=42&team=Team+3&fresh=1");
  });

  it("says above the board when the league's format has no comparison pool", async () => {
    open("/board?league=42&team=Team+3");
    startBoard(document, window, () => succeeding({ benchmark: null }), sources);
    await boardShown();
    expect(noticesShown()).toEqual([NO_BENCHMARK_NOTICE]);
    expect(NO_BENCHMARK_NOTICE).toBe(
      "No comparison pool exists for this league's format yet, so roster depth is graded as average. Calls and deals may differ from a full run.",
    );
    expect(document.body.firstElementChild!.classList.contains("site-notices")).toBe(true);
  });

  it("shows no notice for a report with a benchmark", async () => {
    open("/board?league=42&team=Team+3");
    startBoard(document, window, () => succeeding({ benchmark }), sources);
    await boardShown();
    expect(noticesShown()).toEqual([]);
    expect(document.querySelector(".site-notices")).toBeNull();
  });

  it("shows the run's notices as text", async () => {
    open("/board?league=42&team=Team+3");
    const markup = "<b>not bold</b>";
    startBoard(document, window, () => succeeding({ benchmark: null }, [TRADE_HISTORY_NOTICE, markup]), sources);
    await boardShown();
    expect(noticesShown()).toEqual([NO_BENCHMARK_NOTICE, TRADE_HISTORY_NOTICE, markup]);
    expect(document.querySelector(".site-notices b")).toBeNull();
  });

  it("puts the site's page back with the error and Try again when mounting the board fails", async () => {
    open("/board?league=42&team=Team+3");
    // mountBoard sets the data after it has replaced the page with the board's markup
    Object.defineProperty(window, "__BOARD_DATA__", {
      configurable: true,
      set() {
        throw new Error("the board could not start");
      },
    });
    try {
      const worker = succeeding({ benchmark });
      startBoard(document, window, () => worker, sources);
      await errorShown();
      expect(worker.terminated).toBe(true);
    } finally {
      delete (window as unknown as { __BOARD_DATA__?: unknown }).__BOARD_DATA__;
    }
    expect(document.body.className).toBe("site-page");
    expect([...document.body.children]).toEqual([main()]);
    expect(document.querySelector(".site-message")!.textContent).toBe("the board could not start");
    const again = [...main().querySelectorAll("a")].find((a) => a.textContent === "Try again")!;
    expect(again.getAttribute("href")).toBe("/board?league=42&team=Team+3");
    expect(document.title).toBe("No board · The Rebuild");
  });

  it("makes Try again repeat a normal run without fresh", async () => {
    open("/board?league=42&team=Team+3");
    startBoard(document, window, () => failing("Sleeper is not responding."));
    await errorShown();
    const again = [...main().querySelectorAll("a")].find((a) => a.textContent === "Try again")!;
    expect(again.getAttribute("href")).toBe("/board?league=42&team=Team+3");
  });
});
