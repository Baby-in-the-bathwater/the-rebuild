// The board page: runs the report in the engine worker with a progress list, then shows the CLI's trade board.
import css from "../../../rebuild/templates/board.css?raw";
import body from "../../../rebuild/templates/board_body.html?raw";
import boardJs from "../../../rebuild/templates/board.js?raw";
import weightsJs from "../../../rebuild/templates/board_weights.js?raw";
import { createEngine, type WorkerLike } from "../engine/client";
import { validLeagueId } from "./form";

export type BoardSources = { css: string; body: string; weightsJs: string; boardJs: string };

/** The trade board's own sources, shared with the CLI (see `render` in rebuild/board.py). */
export const BOARD_SOURCES: BoardSources = { css, body, weightsJs, boardJs };

/** The league and team the page is for, or null when either is missing or blank. */
export function parseQuery(search: string): { leagueId: string; team: string } | null {
  const q = new URLSearchParams(search);
  const leagueId = (q.get("league") ?? "").trim();
  const team = (q.get("team") ?? "").trim();
  return leagueId && team ? { leagueId, team } : null;
}

/** Replaces the page with the board, in the order the CLI's file has it: style, markup, data, weights script, board
 * script. The scripts run as classic scripts; the board script declares top-level consts, so mount once per page. */
export function mountBoard(doc: Document, sources: BoardSources, boardData: Record<string, unknown>): void {
  doc.title = `${String(boardData.league)} Trade Board`;
  const style = doc.createElement("style");
  style.textContent = sources.css;
  doc.head.append(style);
  doc.body.removeAttribute("class");
  doc.body.innerHTML = sources.body;
  (doc.defaultView as unknown as { __BOARD_DATA__: unknown }).__BOARD_DATA__ = boardData;
  for (const text of [sources.weightsJs, sources.boardJs]) {
    const script = doc.createElement("script");
    script.textContent = text;
    doc.body.append(script);
  }
}

function el<K extends keyof HTMLElementTagNameMap>(doc: Document, tag: K, attrs: Record<string, string> = {}, text?: string) {
  const node = doc.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (text !== undefined) node.textContent = text;
  return node;
}

/** The site's own controls, fixed in a corner and outside the board's markup. */
function controls(doc: Document, win: Window): HTMLElement {
  const box = el(doc, "nav", { class: "site-controls", "aria-label": "Report" });
  box.append(el(doc, "a", { class: "site-btn", href: "/" }, "New report"));
  const refresh = el(doc, "button", { class: "site-btn", type: "button", title: "Fetch the league again and rebuild" }, "Refresh data");
  refresh.addEventListener("click", () => {
    const url = new URL(win.location.href);
    url.searchParams.set("fresh", "1");
    win.location.replace(url.href);
  });
  box.append(refresh);
  return box;
}

/** Room under the board for the fixed controls, so they never cover its last lines. */
export const CONTROLS_CLEARANCE = "calc(72px + env(safe-area-inset-bottom, 0px))";

export type BoardWorker = WorkerLike & { terminate(): void };
const engineWorker = (): BoardWorker =>
  new Worker(new URL("../engine/worker.ts", import.meta.url), { type: "module" });

/** Runs the board page in `doc`: a progress list, then the board or the error. `createWorker` is for tests. */
export function startBoard(doc: Document, win: Window, createWorker: () => BoardWorker = engineWorker): void {
  const main = doc.getElementById("site-main");
  if (!main) throw new Error("the board page is missing #site-main");
  const query = parseQuery(win.location.search);
  if (!query || !validLeagueId(query.leagueId)) {
    const actions = el(doc, "p", { class: "site-actions" });
    actions.append(el(doc, "a", { class: "site-btn site-primary", href: "/" }, "Open the form"));
    main.replaceChildren(
      el(doc, "h1", { class: "site-title" }, "Which league?"),
      el(doc, "p", { class: "site-lede" }, "This page needs a league id and a team."),
      actions,
    );
    return;
  }

  // ?fresh=1 asks for a rebuild once; drop it so a later reload uses the cached report.
  const url = new URL(win.location.href);
  const fresh = url.searchParams.get("fresh") === "1";
  if (fresh) {
    url.searchParams.delete("fresh");
    win.history.replaceState(win.history.state, "", url.href);
  }

  doc.title = `Building the board · The Rebuild`;
  const steps = el(doc, "ol", { class: "site-progress", "aria-live": "polite" });
  const step = (line: string) => {
    steps.lastElementChild?.classList.add("site-done");
    steps.append(el(doc, "li", {}, line));
  };
  main.replaceChildren(
    el(doc, "h1", { class: "site-title" }, "Building the trade board"),
    el(doc, "p", { class: "site-lede" }, `League ${query.leagueId}, team "${query.team}".`),
    steps,
    el(doc, "p", { class: "site-note" }, "The first run downloads the Python engine (about 13 MB). Later runs reuse it, and a report stays cached for 30 minutes."),
  );
  step("starting");

  // "Try again" repeats this run as it was asked for, fresh or not.
  const again = new URL(url.href);
  if (fresh) again.searchParams.set("fresh", "1");

  const worker = createWorker();
  createEngine(worker)
    .report({ ...query, ...(fresh ? { fresh: true } : {}) }, step)
    .then((report) => {
      worker.terminate();
      mountBoard(doc, BOARD_SOURCES, report.board_data);
      doc.body.append(controls(doc, win));
      doc.body.style.paddingBottom = CONTROLS_CLEARANCE;
    })
    .catch((e: unknown) => {
      worker.terminate();
      doc.title = `No board · The Rebuild`;
      const message = el(doc, "p", { class: "site-message", role: "alert" }, e instanceof Error ? e.message : String(e));
      const actions = el(doc, "p", { class: "site-actions" });
      actions.append(
        el(doc, "a", { class: "site-btn site-primary", href: again.pathname + again.search }, "Try again"),
        el(doc, "a", { class: "site-btn", href: "/" }, "Back to the form"),
      );
      main.replaceChildren(el(doc, "h1", { class: "site-title" }, "No board this time"), message, actions);
      // mountBoard threw after replacing the page (an error inside board.js itself is reported by the browser, not
      // here): put the site's page back so the error screen is styled.
      if (!main.isConnected) {
        doc.body.className = "site-page";
        doc.body.replaceChildren(main);
      }
    });
}
