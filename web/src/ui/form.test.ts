// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from "vitest";
import { boardUrl, LAST_KEY, startForm, validLeagueId } from "./form";

describe("validLeagueId", () => {
  it.each([
    ["1180234567891234560", true],
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

describe("the form", () => {
  const markup = `
    <form id="report-form" novalidate>
      <input id="league" name="league"><input id="team" name="team">
      <p id="form-error" hidden></p>
      <button type="submit">Build</button>
    </form>`;
  let went: string[];
  const submit = () => document.getElementById("report-form")!.dispatchEvent(new Event("submit", { cancelable: true }));
  const field = (id: string) => document.getElementById(id) as HTMLInputElement;

  beforeEach(() => {
    document.body.innerHTML = markup;
    localStorage.clear();
    went = [];
  });

  it("prefills the last league and team", () => {
    localStorage.setItem(LAST_KEY, JSON.stringify({ league: "42", team: "Team 3" }));
    startForm(document, { storage: localStorage, navigate: (u) => went.push(u) });
    expect(field("league").value).toBe("42");
    expect(field("team").value).toBe("Team 3");
  });

  it("shows an inline message and stays put for a league id that is not all digits", () => {
    startForm(document, { storage: localStorage, navigate: (u) => went.push(u) });
    field("league").value = "L1";
    field("team").value = "Team 3";
    submit();
    expect(went).toEqual([]);
    const error = document.getElementById("form-error")!;
    expect(error.hidden).toBe(false);
    expect(error.textContent).toMatch(/digits/);
    expect(localStorage.getItem(LAST_KEY)).toBeNull();
  });

  it("goes to the board and remembers the league and team", () => {
    startForm(document, { storage: localStorage, navigate: (u) => went.push(u) });
    field("league").value = "42";
    field("team").value = "Team 3";
    submit();
    expect(went).toEqual(["/board?league=42&team=Team+3"]);
    expect(JSON.parse(localStorage.getItem(LAST_KEY)!)).toEqual({ league: "42", team: "Team 3" });
  });

  it("asks for a team when the team is blank", () => {
    startForm(document, { storage: localStorage, navigate: (u) => went.push(u) });
    field("league").value = "42";
    submit();
    expect(went).toEqual([]);
    expect(document.getElementById("form-error")!.textContent).toMatch(/team/i);
  });

  it("works without storage", () => {
    startForm(document, { storage: null, navigate: (u) => went.push(u) });
    field("league").value = "42";
    field("team").value = "1";
    submit();
    expect(went).toEqual(["/board?league=42&team=1"]);
  });
});
