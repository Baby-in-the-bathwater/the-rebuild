// @vitest-environment jsdom
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { beforeEach, describe, expect, it } from "vitest";
import { LookupError, type Found } from "../data/user";
import { webRoot } from "../testing/fixture";
import { boardUrl, LAST_KEY, startForm, validLeagueId, type FormOptions } from "./form";

describe("validLeagueId", () => {
  it.each([
    ["1".repeat(19), true], // as long as a real league id, built at run time so no id-shaped literal is committed
    ["42", true],
    ["  42 ", true],
    ["", false],
    ["   ", false],
    ["L1", false],
    ["12a4", false],
    ["-12", false],
    ["1.5", false],
    ["1 2", false],
  ])("%j -> %s", (text, valid) => {
    expect(validLeagueId(text)).toBe(valid);
  });
});

describe("boardUrl", () => {
  it("puts the trimmed league and team in the query", () => {
    expect(boardUrl(" 42 ", "  Team & Co ")).toBe("/board?league=42&team=Team+%26+Co");
  });
});

// The page's own markup, so the tests cannot drift from index.html.
const markup = /<main[^>]*>([\s\S]*)<\/main>/.exec(readFileSync(join(webRoot, "index.html"), "utf8"))![1]!;

const teams = (n: number) => [...Array(n)].map((_, i) => ({ rosterId: i + 1, name: `Team ${i + 1}`, manager: `Manager ${i + 1}` }));
const FOUND: Found = {
  username: "manager3",
  displayName: "Manager 3",
  season: "2026",
  leagues: [
    { leagueId: "41", name: "Alpha League", season: "2026", format: "12-team dynasty · Superflex · half PPR", teams: teams(12), own: 3 },
    { leagueId: "42", name: "Beta League", season: "2026", format: "10-team redraft · 1QB · PPR", teams: teams(10), own: 7 },
  ],
};

describe("the form page", () => {
  let went: string[];
  let lookups: string[];
  let answer: (username: string) => Promise<Found>;
  const start = (storage: Storage | null = localStorage) => {
    const opts: FormOptions = {
      storage,
      navigate: (u) => went.push(u),
      findLeagues: (username) => {
        lookups.push(username);
        return answer(username);
      },
    };
    startForm(document, opts);
  };
  const submit = (id: string) => document.getElementById(id)!.dispatchEvent(new Event("submit", { cancelable: true }));
  const field = (id: string) => document.getElementById(id) as HTMLInputElement;
  const el = (id: string) => document.getElementById(id)!;
  const settle = () => new Promise((resolve) => setTimeout(resolve, 0));
  const stored = () => JSON.parse(localStorage.getItem(LAST_KEY) ?? "null");
  const radios = () => [...document.querySelectorAll<HTMLInputElement>('#leagues input[type="radio"]')];
  const find = async (name = "manager3") => {
    field("username").value = name;
    submit("user-form");
    await settle();
  };

  beforeEach(() => {
    document.body.innerHTML = markup;
    localStorage.clear();
    went = [];
    lookups = [];
    answer = async () => FOUND;
  });

  describe("by username", () => {
    it("lists the user's leagues with the first chosen and their own team selected", async () => {
      start();
      expect(el("pick-form").hidden).toBe(true);
      await find();
      expect(lookups).toEqual(["manager3"]);
      expect(el("pick-form").hidden).toBe(false);
      expect(el("pick-title").textContent).toBe("Manager 3's leagues, 2026");
      expect(radios().map((r) => [r.value, r.checked])).toEqual([["41", true], ["42", false]]);
      const cards = [...document.querySelectorAll(".site-league")].map((c) => c.textContent);
      expect(cards[0]).toContain("Alpha League");
      expect(cards[0]).toContain("12-team dynasty · Superflex · half PPR");
      expect(cards[0]).toContain("Your team: Team 3");
      const select = el("pick-team") as HTMLSelectElement;
      expect(select.options).toHaveLength(12);
      expect(select.value).toBe("3");
      expect(select.selectedOptions[0]!.textContent).toBe("Team 3 (Manager 3) · your team");
      expect(document.activeElement).toBe(el("pick-title"));
    });

    it("goes to the board for the chosen league with the team's roster number, and remembers all three", async () => {
      start();
      await find();
      submit("pick-form");
      expect(went).toEqual(["/board?league=41&team=3"]);
      expect(stored()).toEqual({ league: "41", team: "3", username: "manager3" });
    });

    it("switches the team choices with the league, and lets another team be picked", async () => {
      start();
      await find();
      radios()[1]!.checked = true;
      radios()[1]!.dispatchEvent(new Event("change"));
      const select = el("pick-team") as HTMLSelectElement;
      expect(select.options).toHaveLength(10);
      expect(select.value).toBe("7");
      select.value = "2";
      submit("pick-form");
      expect(went).toEqual(["/board?league=42&team=2"]);
    });

    it("remembers the username as soon as it is found, keeping the last league and team", async () => {
      localStorage.setItem(LAST_KEY, JSON.stringify({ league: "42", team: "2" }));
      start();
      await find(" Manager3 ");
      expect(stored()).toEqual({ league: "42", team: "2", username: "manager3" });
    });

    it("prefills the last username, and chooses the last league and team again", async () => {
      localStorage.setItem(LAST_KEY, JSON.stringify({ league: "42", team: "2", username: "manager3" }));
      start();
      expect(field("username").value).toBe("manager3");
      expect((el("by-id") as HTMLDetailsElement).open).toBe(false);
      await find();
      expect(radios().map((r) => r.checked)).toEqual([false, true]);
      expect((el("pick-team") as HTMLSelectElement).value).toBe("2");
    });

    it("shows an unknown username's message on the field and no leagues", async () => {
      answer = async () => {
        throw new LookupError("username", 'Sleeper has no user called "nobody".');
      };
      start();
      await find("nobody");
      expect(el("user-error").hidden).toBe(false);
      expect(el("user-error").textContent).toBe('Sleeper has no user called "nobody".');
      expect(field("username").getAttribute("aria-invalid")).toBe("true");
      expect(el("pick-form").hidden).toBe(true);
      expect(stored()).toBeNull();
    });

    it("shows that a user has no leagues without blaming the username", async () => {
      answer = async () => {
        throw new LookupError("leagues", "Manager 3 is not in any NFL league on Sleeper for 2026 or 2025.");
      };
      start();
      await find();
      expect(el("user-error").textContent).toMatch(/not in any NFL league/);
      expect(field("username").hasAttribute("aria-invalid")).toBe(false);
    });

    it("lets the lookup be tried again after Sleeper did not answer", async () => {
      answer = async () => {
        throw new LookupError("sleeper", "Sleeper is not answering right now. Wait a minute, then try again.");
      };
      start();
      await find();
      const button = el("find") as HTMLButtonElement;
      expect(el("user-error").textContent).toMatch(/try again/);
      expect(button.disabled).toBe(false);
      expect(button.textContent).toBe("Find my leagues");
      answer = async () => FOUND;
      await find();
      expect(el("user-error").hidden).toBe(true);
      expect(el("pick-form").hidden).toBe(false);
    });

    it("gives a plain message for a failure it does not know", async () => {
      answer = async () => {
        throw new Error("boom");
      };
      start();
      await find();
      expect(el("user-error").textContent).toMatch(/Check your connection/);
    });

    it("shows the button as busy while looking, and drops the answer of a lookup that was replaced", async () => {
      let release!: (found: Found) => void;
      answer = () => new Promise<Found>((resolve) => (release = resolve));
      start();
      field("username").value = "first";
      submit("user-form");
      const button = el("find") as HTMLButtonElement;
      expect(button.disabled).toBe(true);
      const releaseFirst = release;
      answer = async () => ({ ...FOUND, displayName: "Second" });
      await find("second");
      releaseFirst({ ...FOUND, displayName: "First" });
      await settle();
      expect(el("pick-title").textContent).toBe("Second's leagues, 2026");
      expect(button.disabled).toBe(false);
    });

    it("asks for a team in a league where the user owns none", async () => {
      answer = async () => ({ ...FOUND, leagues: [{ ...FOUND.leagues[0]!, own: null }] });
      start();
      await find();
      expect(document.querySelector(".site-league")!.textContent).toContain("You have no team in this league");
      expect((el("pick-team") as HTMLSelectElement).value).toBe("");
      submit("pick-form");
      expect(went).toEqual([]);
      expect(el("pick-error").hidden).toBe(false);
      (el("pick-team") as HTMLSelectElement).value = "4";
      submit("pick-form");
      expect(went).toEqual(["/board?league=41&team=4"]);
    });

    it("writes league and team names as text, never as markup", async () => {
      const hostile = '<img src=x onerror="window.__pwned = 1">';
      answer = async () => ({
        ...FOUND,
        displayName: hostile,
        leagues: [{ ...FOUND.leagues[0]!, name: hostile, format: hostile, teams: [{ rosterId: 3, name: hostile, manager: hostile }] }],
      });
      start();
      await find();
      expect(el("pick-form").querySelector("img")).toBeNull();
      expect(document.querySelector(".site-league-name")!.textContent).toBe(hostile);
      expect((el("pick-team") as HTMLSelectElement).options[0]!.textContent).toBe(`${hostile} · your team`);
    });
  });

  describe("by league id", () => {
    it("prefills the last league and team, and opens the league id form for someone who has only used it", () => {
      localStorage.setItem(LAST_KEY, JSON.stringify({ league: "42", team: "Team 3" }));
      start();
      expect(field("league").value).toBe("42");
      expect(field("team").value).toBe("Team 3");
      expect((el("by-id") as HTMLDetailsElement).open).toBe(true);
    });

    it("keeps the league id form closed on a first visit", () => {
      start();
      expect((el("by-id") as HTMLDetailsElement).open).toBe(false);
    });

    it("shows an inline message and stays put for a league id that is not all digits", () => {
      start();
      field("league").value = "L1";
      field("team").value = "Team 3";
      submit("report-form");
      expect(went).toEqual([]);
      const error = el("form-error");
      expect(error.hidden).toBe(false);
      expect(error.textContent).toMatch(/digits/);
      expect(localStorage.getItem(LAST_KEY)).toBeNull();
    });

    it("goes to the board and remembers the league and team", () => {
      start();
      field("league").value = "42";
      field("team").value = "Team 3";
      submit("report-form");
      expect(went).toEqual(["/board?league=42&team=Team+3"]);
      expect(stored()).toEqual({ league: "42", team: "Team 3" });
    });

    it("keeps a remembered username when a league id is used", () => {
      localStorage.setItem(LAST_KEY, JSON.stringify({ league: "", team: "", username: "manager3" }));
      start();
      expect(field("league").value).toBe("");
      field("league").value = "42";
      field("team").value = "1";
      submit("report-form");
      expect(stored()).toEqual({ league: "42", team: "1", username: "manager3" });
    });

    it("asks for a team when the team is blank", () => {
      start();
      field("league").value = "42";
      submit("report-form");
      expect(went).toEqual([]);
      expect(el("form-error").textContent).toMatch(/team/i);
    });

    it("works without storage", async () => {
      start(null);
      await find();
      submit("pick-form");
      field("league").value = "42";
      field("team").value = "1";
      submit("report-form");
      expect(went).toEqual(["/board?league=41&team=3", "/board?league=42&team=1"]);
    });
  });
});
