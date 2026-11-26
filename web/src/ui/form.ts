// The form page: a Sleeper league id and a team, remembered between visits, leading to the board page.

/** Where the last league and team entered are remembered. */
export const LAST_KEY = "rebuild-last";

/** A Sleeper league id is all digits. */
export function validLeagueId(text: string): boolean {
  return /^\d+$/.test(text.trim());
}

export function boardUrl(leagueId: string, team: string): string {
  return `/board?${new URLSearchParams({ league: leagueId.trim(), team: team.trim() })}`;
}

type Last = { league: string; team: string };

function readLast(storage: Storage | null): Last | null {
  try {
    const held = JSON.parse(storage?.getItem(LAST_KEY) ?? "null") as Partial<Last> | null;
    return held && typeof held.league === "string" && typeof held.team === "string" ? (held as Last) : null;
  } catch {
    return null;
  }
}

function writeLast(storage: Storage | null, last: Last): void {
  try {
    storage?.setItem(LAST_KEY, JSON.stringify(last));
  } catch {
    // remembering is a convenience; never block the report on it
  }
}

/** Wires up the form in `doc` (#report-form with #league, #team and #form-error). */
export function startForm(doc: Document, opts: { storage: Storage | null; navigate: (url: string) => void }): void {
  const form = doc.getElementById("report-form") as HTMLFormElement | null;
  const league = doc.getElementById("league") as HTMLInputElement | null;
  const team = doc.getElementById("team") as HTMLInputElement | null;
  const error = doc.getElementById("form-error");
  if (!form || !league || !team || !error) throw new Error("the form page is missing its form");

  const last = readLast(opts.storage);
  if (last) {
    league.value = last.league;
    team.value = last.team;
  }

  const show = (message: string, field: HTMLInputElement) => {
    error.textContent = message;
    error.hidden = false;
    field.setAttribute("aria-invalid", "true");
    field.focus();
  };

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    league.removeAttribute("aria-invalid");
    team.removeAttribute("aria-invalid");
    error.hidden = true;
    if (!validLeagueId(league.value)) {
      show("A league id is all digits: the long number in your league's address on sleeper.com.", league);
      return;
    }
    if (team.value.trim() === "") {
      show("Enter your team: its name, your manager name or its roster number.", team);
      return;
    }
    writeLast(opts.storage, { league: league.value.trim(), team: team.value.trim() });
    opts.navigate(boardUrl(league.value, team.value));
  });
}
