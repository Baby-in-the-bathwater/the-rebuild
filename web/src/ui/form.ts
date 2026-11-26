// The form page: a Sleeper username leads to the user's leagues, a league and a team, then the board page.
// A league id and a team can still be typed in directly. The last entries are remembered between visits.
import { LookupError, type Found, type FoundLeague } from "../data/user";

/** Where the last username, league and team entered are remembered. */
export const LAST_KEY = "rebuild-last";

/** A Sleeper league id is all digits. */
export function validLeagueId(text: string): boolean {
  return /^\d+$/.test(text.trim());
}

export function boardUrl(leagueId: string, team: string): string {
  return `/board?${new URLSearchParams({ league: leagueId.trim(), team: team.trim() })}`;
}

/** `league` and `team` are "" until a report has been asked for; `username` is absent until one has been found. */
type Last = { league: string; team: string; username?: string };

function readLast(storage: Storage | null): Last | null {
  try {
    const held = JSON.parse(storage?.getItem(LAST_KEY) ?? "null") as Partial<Last> | null;
    if (!held || typeof held.league !== "string" || typeof held.team !== "string") return null;
    return { league: held.league, team: held.team, ...(typeof held.username === "string" ? { username: held.username } : {}) };
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

export type FormOptions = {
  storage: Storage | null;
  navigate: (url: string) => void;
  /** Looks a username up (`findLeagues` over the real Sleeper client on the site). Rejects with `LookupError`. */
  findLeagues: (username: string) => Promise<Found>;
};

function el<K extends keyof HTMLElementTagNameMap>(doc: Document, tag: K, attrs: Record<string, string> = {}, text?: string) {
  const node = doc.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (text !== undefined) node.textContent = text;
  return node;
}

/** The team name with its manager, unless they are the same or the roster has no owner. */
const teamLabel = (t: FoundLeague["teams"][number]) => (t.manager && t.manager !== t.name ? `${t.name} (${t.manager})` : t.name);

/** Wires up the form page in `doc`: the username form (#user-form), the league picker it fills (#pick-form) and the
 * league id form (#report-form, inside the #by-id disclosure). */
export function startForm(doc: Document, opts: FormOptions): void {
  const need = <T extends HTMLElement>(id: string): T => {
    const node = doc.getElementById(id) as T | null;
    if (!node) throw new Error(`the form page is missing #${id}`);
    return node;
  };
  const userForm = need<HTMLFormElement>("user-form");
  const username = need<HTMLInputElement>("username");
  const userError = need("user-error");
  const find = need<HTMLButtonElement>("find");
  const pickForm = need<HTMLFormElement>("pick-form");
  const pickTitle = need("pick-title");
  const leagueList = need("leagues");
  const pickTeam = need<HTMLSelectElement>("pick-team");
  const pickError = need("pick-error");
  const byId = need<HTMLDetailsElement>("by-id");
  const form = need<HTMLFormElement>("report-form");
  const league = need<HTMLInputElement>("league");
  const team = need<HTMLInputElement>("team");
  const error = need("form-error");

  let last = readLast(opts.storage);
  if (last?.username) username.value = last.username;
  if (last?.league) {
    league.value = last.league;
    team.value = last.team;
    // Someone who typed a league id last time, and has never looked a username up, gets that form open.
    if (!last.username) byId.open = true;
  }
  const remember = (next: Last) => {
    last = next;
    writeLast(opts.storage, next);
  };

  // ---- username -> leagues
  let found: Found | null = null;
  let asked = 0; // the lookup in flight; an older one's answer is dropped

  const chosen = (): FoundLeague | null => {
    const picked = leagueList.querySelector<HTMLInputElement>('input[name="pick-league"]:checked');
    return found?.leagues.find((l) => l.leagueId === picked?.value) ?? null;
  };

  /** The team choices for the chosen league, with the user's own team selected (or the remembered one, for the
   * remembered league). */
  const showTeams = () => {
    const lg = chosen();
    pickTeam.replaceChildren();
    pickError.hidden = true;
    if (!lg) return;
    if (lg.own === null) pickTeam.append(el(doc, "option", { value: "" }, "Choose a team"));
    for (const t of lg.teams) {
      const text = teamLabel(t) + (t.rosterId === lg.own ? " · your team" : "");
      pickTeam.append(el(doc, "option", { value: String(t.rosterId) }, text));
    }
    const kept = last && last.league === lg.leagueId && lg.teams.some((t) => String(t.rosterId) === last!.team) ? last.team : null;
    pickTeam.value = kept ?? (lg.own === null ? "" : String(lg.own));
  };

  const showLeagues = (result: Found) => {
    found = result;
    pickTitle.textContent = `${result.displayName}'s leagues, ${result.season}`;
    leagueList.replaceChildren();
    for (const lg of result.leagues) {
      const mine = lg.teams.find((t) => t.rosterId === lg.own);
      const card = el(doc, "label", { class: "site-league" });
      const text = el(doc, "span", { class: "site-league-text" });
      text.append(
        el(doc, "span", { class: "site-league-name" }, lg.name),
        el(doc, "span", { class: "site-league-meta" }, lg.format),
        el(doc, "span", { class: "site-league-meta" }, mine ? `Your team: ${mine.name}` : "You have no team in this league"),
      );
      card.append(el(doc, "input", { type: "radio", name: "pick-league", value: lg.leagueId }), text);
      leagueList.append(card);
    }
    const radios = [...leagueList.querySelectorAll<HTMLInputElement>('input[name="pick-league"]')];
    const first = radios.find((r) => r.value === last?.league) ?? radios[0];
    if (first) first.checked = true;
    for (const r of radios) r.addEventListener("change", showTeams);
    showTeams();
    pickForm.hidden = false;
    pickTitle.focus();
  };

  userForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const mine = ++asked;
    userError.hidden = true;
    username.removeAttribute("aria-invalid");
    pickForm.hidden = true;
    found = null;
    find.disabled = true;
    find.textContent = "Looking…";
    opts
      .findLeagues(username.value)
      .then((result) => {
        if (mine !== asked) return;
        remember({ league: last?.league ?? "", team: last?.team ?? "", username: result.username });
        showLeagues(result);
      })
      .catch((err: unknown) => {
        if (mine !== asked) return;
        const known = err instanceof LookupError;
        userError.textContent = known ? err.message : "The lookup failed. Check your connection, then try again.";
        userError.hidden = false;
        // A wrong username is the field's fault; no leagues or no answer from Sleeper is not.
        if (known && err.kind === "username") username.setAttribute("aria-invalid", "true");
        username.focus();
      })
      .finally(() => {
        if (mine !== asked) return;
        find.disabled = false;
        find.textContent = "Find my leagues";
      });
  });

  pickForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const lg = chosen();
    if (!lg || pickTeam.value === "") {
      pickError.textContent = lg ? "Choose a team to build the board for." : "Choose a league.";
      pickError.hidden = false;
      (lg ? pickTeam : leagueList.querySelector<HTMLInputElement>("input"))?.focus();
      return;
    }
    // The roster number, not the name: two teams can share a name, and the engine reads a short number as a roster.
    remember({ league: lg.leagueId, team: pickTeam.value, ...(found ? { username: found.username } : {}) });
    opts.navigate(boardUrl(lg.leagueId, pickTeam.value));
  });

  // ---- a league id, typed in
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
    remember({ league: league.value.trim(), team: team.value.trim(), ...(last?.username ? { username: last.username } : {}) });
    opts.navigate(boardUrl(league.value, team.value));
  });
}
