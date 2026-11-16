import { JSDOM, VirtualConsole } from "jsdom";
import { beforeAll, describe, expect, it } from "vitest";
import { fixtureText } from "../testing/fixture";
import { BOARD_SOURCES, mountBoard, parseQuery } from "./board";

describe("parseQuery", () => {
  it.each([
    ["?league=42&team=Team%203", { leagueId: "42", team: "Team 3" }],
    ["league=42&team=Team+3", { leagueId: "42", team: "Team 3" }],
    ["?team=%20Team%203%20&league=%2042%20", { leagueId: "42", team: "Team 3" }],
    ["?league=42&team=Team+3&fresh=1", { leagueId: "42", team: "Team 3" }],
    ["?league=42", null],
    ["?team=Team+3", null],
    ["?league=&team=Team+3", null],
    ["?league=42&team=%20%20", null],
    ["", null],
  ])("%j", (search, parsed) => {
    expect(parseQuery(search)).toEqual(parsed);
  });
});

// The board script declares top-level consts, so it can run once per document: one mount for the whole file, in a
// window of its own (Vitest's jsdom environment hides properties set on its window from the scripts the page runs).
describe("mountBoard", () => {
  const data = JSON.parse(fixtureText("expected/board-data.json")) as {
    league: string;
    league_id: string;
    me_rid: number;
    teams: { rid: number; name: string }[];
  };
  const errors: unknown[] = [];
  const virtualConsole = new VirtualConsole();
  virtualConsole.on("jsdomError", (e) => errors.push(e));
  const dom = new JSDOM("<!doctype html><html><head></head><body class=\"site-page\"><main id=\"site-main\">progress</main></body></html>", {
    url: "http://localhost/board?league=L1&team=Team+3",
    runScripts: "dangerously",
    pretendToBeVisual: true,
    virtualConsole,
  });
  const { window } = dom;
  const { document } = window;
  const stored = () =>
    JSON.parse(window.localStorage.getItem(`rebuild-board-${data.league_id}`) ?? "null") as { team?: number } | null;

  beforeAll(() => {
    mountBoard(document, BOARD_SOURCES, data);
  });

  it("runs the board without an error", () => {
    expect(errors).toEqual([]);
  });

  it("sets the title the CLI sets", () => {
    expect(document.title).toBe(`${data.league} Trade Board`);
  });

  it("puts the board's style, markup and data in the document", () => {
    expect([...document.head.querySelectorAll("style")].some((s) => s.textContent === BOARD_SOURCES.css)).toBe(true);
    expect(document.getElementById("rosters")).not.toBeNull();
    expect(document.getElementById("site-main")).toBeNull();
    expect(document.body.className).toBe("");
    expect((window as unknown as { __BOARD_DATA__: unknown }).__BOARD_DATA__).toBe(data);
    const scripts = [...document.body.querySelectorAll("script")].map((s) => s.textContent);
    expect(scripts).toEqual([BOARD_SOURCES.weightsJs, BOARD_SOURCES.boardJs]);
  });

  it("renders every team name", () => {
    const text = document.getElementById("tabs")!.textContent! + document.getElementById("rosters")!.textContent!;
    for (const { name } of data.teams) {
      const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      expect(text).toMatch(new RegExp(`${escaped}(?!\\d)`));
    }
  });

  it("stores the selection under the league's key when another team is chosen", () => {
    const before = stored()?.team;
    const tab = [...document.querySelectorAll<HTMLButtonElement>("#tabs .tab")].find(
      (b) => b.getAttribute("aria-selected") === "false",
    );
    expect(tab).toBeDefined();
    tab!.click();
    expect(errors).toEqual([]);
    const after = stored()?.team;
    expect(after).toBe(Number(tab!.dataset.team));
    expect(after).not.toBe(before);
  });
});
