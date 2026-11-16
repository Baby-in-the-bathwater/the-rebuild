// @vitest-environment jsdom
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { EngineRequest, EngineResponse } from "../engine/protocol";
import { startBoard, type BoardWorker } from "./board";
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

  it("makes Try again repeat a normal run without fresh", async () => {
    open("/board?league=42&team=Team+3");
    startBoard(document, window, () => failing("Sleeper is not responding."));
    await errorShown();
    const again = [...main().querySelectorAll("a")].find((a) => a.textContent === "Try again")!;
    expect(again.getAttribute("href")).toBe("/board?league=42&team=Team+3");
  });
});
