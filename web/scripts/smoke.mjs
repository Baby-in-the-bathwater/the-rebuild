// Smoke test in a real browser: the built site under `wrangler dev`, headless Chrome, Sleeper and GitHub answered
// from the synthetic fixture. Not part of CI. Run `pnpm build` first, then `node scripts/smoke.mjs`. It serves a
// temporary copy of dist/ and leaves dist/ unchanged.
//
//   SMOKE_PUPPETEER  folder holding puppeteer-core (default: the spike's node_modules)
//   SMOKE_CHROME     Chrome executable (default: the macOS install)
//   SMOKE_PORT       port for wrangler dev (default 8787)
//   SMOKE_SHOT       if set, a PNG path for a screenshot of the first board
//   SMOKE_SHOT_FORM  if set, a PNG path for a screenshot of the form page with the league list
//   SMOKE_SHOT_PHONE if set, a PNG path for a full-page screenshot of the board at phone width
import { spawn } from "node:child_process";
import { copyFileSync, cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { createRequire } from "node:module";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const web = join(dirname(fileURLToPath(import.meta.url)), "..");
const fixture = join(web, "fixtures", "synth");
const dist = join(web, "dist");
const PUPPETEER = process.env.SMOKE_PUPPETEER ?? "/Users/dylan.goings/source/the-rebuild/spike/pyodide/node_modules";
const CHROME = process.env.SMOKE_CHROME ?? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const PORT = Number(process.env.SMOKE_PORT ?? 8787);
const ORIGIN = `http://127.0.0.1:${PORT}`;

const { default: puppeteer } = await import(
  pathToFileURL(createRequire(join(PUPPETEER, "noop.js")).resolve("puppeteer-core")).href
);

// The fixture's league id ("L1") is not all digits, so the form would refuse it. The browser uses a made-up numeric
// id instead, and the fixture answers for it: in urls it reads as L1, and in bodies the JSON string "L1" reads as it.
const meta = JSON.parse(readFileSync(join(fixture, "meta.json"), "utf8"));
const ALIAS = "9000001";
const UNKNOWN = "9000002"; // not in the fixture: every Sleeper request for it is answered 404
const http = JSON.parse(readFileSync(join(fixture, "http.json"), "utf8"));
const expected = JSON.parse(readFileSync(join(fixture, "expected", "board-data.json"), "utf8"));
const INTERCEPTED = new Set(["api.sleeper.app", "raw.githubusercontent.com"]);
const ALLOWED = new Set([new URL(ORIGIN).host, ...INTERCEPTED, "fonts.googleapis.com", "fonts.gstatic.com"]);

// The username lookup's two requests are not part of a report, so the fixture has no answer for them: they are made
// here from the fixture's own league and its first manager whose team is the fixture's team.
const SLEEPER = "https://api.sleeper.app/v1";
const league = JSON.parse(http[`${SLEEPER}/league/${meta.league_id}`]);
const manager = JSON.parse(http[`${SLEEPER}/league/${meta.league_id}/users`]).find((u) => u.metadata?.team_name === meta.team);
const lookups = {
  [`${SLEEPER}/user/${manager.username}`]: JSON.stringify(manager),
  [`${SLEEPER}/user/${manager.user_id}/leagues/nfl/${league.season}`]: JSON.stringify([league]),
  [`${SLEEPER}/user/nobody-here`]: "null",
};

function answer(url) {
  const asFixture = url.replaceAll(`/league/${ALIAS}`, `/league/${meta.league_id}`);
  const body = http[asFixture] ?? lookups[asFixture];
  return body === undefined ? undefined : body.replaceAll(JSON.stringify(meta.league_id), JSON.stringify(ALIAS));
}

const fail = (message) => {
  throw new Error(`smoke: ${message}`);
};

if (!existsSync(join(dist, "board.html"))) fail("no dist/board.html: run `pnpm build` first");

// Serve a copy of dist/ from outside the repo, with the fixture's data added there, so dist/ itself never holds
// synthetic data that a later deploy could ship.
const site = mkdtempSync(join(tmpdir(), "rebuild-smoke-"));
const assets = join(site, "assets");
cpSync(dist, assets, { recursive: true });
mkdirSync(join(assets, "data"), { recursive: true });
for (const name of ["players.json", "snapshot_index.json"]) copyFileSync(join(fixture, name), join(assets, "data", name));

let server = null;
let cleaned = false;
/** Stops wrangler dev and its workerd (the whole process group) and removes the copy. Safe to call twice. */
function cleanup() {
  if (cleaned) return;
  cleaned = true;
  if (server?.pid) {
    try {
      process.kill(-server.pid, "SIGTERM");
    } catch {
      // already gone
    }
  }
  rmSync(site, { recursive: true, force: true });
}
process.on("exit", cleanup);
for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => process.exit(130));

const portFree = () =>
  new Promise((resolve) => {
    const probe = createServer();
    probe.once("error", () => resolve(false));
    probe.listen(PORT, "127.0.0.1", () => probe.close(() => resolve(true)));
  });
if (!(await portFree())) fail(`port ${PORT} is already in use (another wrangler dev?); stop it or set SMOKE_PORT`);

// wrangler.jsonc still applies (not_found_handling, html_handling); --assets only points it at the copy.
server = spawn(
  "pnpm",
  ["exec", "wrangler", "dev", "--ip", "127.0.0.1", "--port", String(PORT), "--assets", assets, "--persist-to", join(site, "state")],
  { cwd: web, env: { ...process.env, WRANGLER_SEND_METRICS: "false" }, stdio: ["ignore", "pipe", "pipe"], detached: true },
);
let serverLog = "";
server.stdout.on("data", (d) => (serverLog += d));
server.stderr.on("data", (d) => (serverLog += d));

async function waitForServer() {
  for (let i = 0; i < 120; i++) {
    try {
      if ((await fetch(`${ORIGIN}/`)).ok) return;
    } catch {
      // not up yet
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  fail(`wrangler dev did not start:\n${serverLog}`);
}

await waitForServer();
const notFound = await fetch(`${ORIGIN}/no-such-page`);
if (notFound.status !== 404 || !(await notFound.text()).includes("Not found")) fail(`/no-such-page answered ${notFound.status} without the 404 page`);
const browser = await puppeteer.launch({ executablePath: CHROME, headless: true, args: ["--no-first-run"] });

const problems = [];
const requests = [];
const failed = [];
let intercepted = 0;

function watch(page) {
  page.on("console", (m) => m.type() === "error" && problems.push(`console: ${m.text()}`));
  page.on("pageerror", (e) => problems.push(`page error: ${e.message}`));
  page.on("response", (res) => res.status() >= 400 && failed.push(`${res.status()} ${res.url()}`));
  page.on("workercreated", (w) => w.on?.("console", (m) => m.type() === "error" && problems.push(`worker console: ${m.text()}`)));
  page.on("request", (req) => {
    const url = new URL(req.url());
    if (url.protocol !== "http:" && url.protocol !== "https:") return void req.continue();
    requests.push(req.url());
    if (!INTERCEPTED.has(url.host)) return void req.continue();
    intercepted++;
    const body = answer(req.url());
    const headers = { "access-control-allow-origin": "*" };
    req.respond(
      body === undefined
        ? { status: 404, headers, contentType: "text/plain", body: "not found" }
        : { status: 200, headers, contentType: url.host === "api.sleeper.app" ? "application/json" : "text/plain", body },
    );
  });
}

const seconds = (ms) => `${(ms / 1000).toFixed(2)} s`;
const visible = (page, text) =>
  page.evaluate((t) => [...document.querySelectorAll("#tabs .tab, #rosters h2")].some((n) => n.textContent.includes(t) && n.getBoundingClientRect().height > 0), text);

try {
  const page = await browser.newPage();
  await page.setRequestInterception(true);
  watch(page);
  // Timings are taken in the page (ms since the board page's navigation): the progress list is gone once the board
  // replaces it, so polling from here could miss the "engine ready" line.
  await page.evaluateOnNewDocument(() => {
    const marks = (window.__smoke = { lines: [] });
    new MutationObserver(() => {
      for (const li of document.querySelectorAll(".site-progress li")) if (!marks.lines.includes(li.textContent)) marks.lines.push(li.textContent);
      if (marks.engineReady === undefined && [...document.querySelectorAll(".site-progress li")].some((li) => li.textContent === "engine ready"))
        marks.engineReady = performance.now();
      if (marks.board === undefined && document.querySelector("#rosters .panel")) marks.board = performance.now();
    }).observe(document, { childList: true, subtree: true });
  });
  const team = expected.teams.find((t) => t.rid !== expected.me_rid).name;

  // 1. The league id form, behind its link, refuses a league id that is not all digits.
  await page.goto(`${ORIGIN}/`, { waitUntil: "load" });
  await page.click("#by-id > summary");
  await page.type("#league", meta.league_id);
  await page.type("#team", meta.team);
  await page.click("#report-form button[type=submit]");
  await page.waitForSelector("#form-error:not([hidden])");
  if (new URL(page.url()).pathname !== "/") fail(`an invalid league id navigated to ${page.url()}`);

  // 1b. An unknown username gets a message; a known one lists its league with the user's own team selected, and
  // "Build the trade board" goes to the board for that league and roster. Meanwhile the page has fetched the
  // engine's files, so the board page finds them in the cache.
  await page.type("#username", "nobody-here");
  await page.click("#find");
  await page.waitForSelector("#user-error:not([hidden])");
  const unknownUser = await page.$eval("#user-error", (n) => n.textContent);
  if (!unknownUser.includes("nobody-here")) fail(`an unknown username showed: "${unknownUser}"`);
  await page.$eval("#username", (n) => (n.value = ""));
  await page.type("#username", manager.username);
  await page.click("#find");
  await page.waitForSelector("#pick-form:not([hidden])");
  const pick = await page.evaluate(() => ({
    leagues: [...document.querySelectorAll(".site-league")].map((n) => n.textContent),
    chosen: document.querySelector("#leagues input:checked")?.value,
    team: document.querySelector("#pick-team").selectedOptions[0]?.textContent,
    sideways: document.documentElement.scrollWidth - document.documentElement.clientWidth,
  }));
  if (pick.leagues.length !== 1 || !pick.leagues[0].includes(league.name)) fail(`the league list is ${JSON.stringify(pick.leagues)}`);
  if (pick.chosen !== ALIAS) fail(`the chosen league is ${pick.chosen}, not ${ALIAS}`);
  if (!pick.team?.startsWith(meta.team)) fail(`the selected team is "${pick.team}", not ${meta.team}`);
  if (process.env.SMOKE_SHOT_FORM) await page.screenshot({ path: process.env.SMOKE_SHOT_FORM, fullPage: true });
  const warmed = ["/engine/engine.zip", "pyodide.asm.wasm"].filter((name) => !requests.some((u) => u.endsWith(name)));
  if (warmed.length) fail(`the form page did not fetch ${warmed.join(", ")} ahead of time`);
  await Promise.all([page.waitForNavigation(), page.click("#pick-form button[type=submit]")]);
  const boardUrl = page.url();
  if (!/[?&]team=\d+$/.test(boardUrl)) fail(`the board address does not carry a roster number: ${boardUrl}`);
  console.log(`username -> ${boardUrl.replace(ORIGIN, "")}`);

  // 2. Progress, then the board.
  await page.waitForSelector("#rosters .panel", { timeout: 120_000 });
  const first = await page.evaluate(() => window.__smoke);
  if (first.engineReady === undefined) fail(`the progress list never said the engine was ready: ${JSON.stringify(first.lines)}`);
  if (!(await visible(page, team))) fail(`team "${team}" is not visible on the board`);
  const title = await page.title();
  if (title !== `${expected.league} Trade Board`) fail(`title is "${title}"`);
  if (!(await page.$(".site-controls"))) fail("no site controls over the board");
  if (!(await page.evaluate(() => document.body.style.paddingBottom))) fail("no room under the board for the controls");
  if (process.env.SMOKE_SHOT) await page.screenshot({ path: process.env.SMOKE_SHOT });
  const strangers = requests.filter((u) => !ALLOWED.has(new URL(u).host));
  if (strangers.length) fail(`requests to other hosts: ${strangers.join(", ")}`);
  if (intercepted === 0) fail("no Sleeper or GitHub request was intercepted (are worker requests reaching interception?)");
  if (problems.length) fail(`errors on the first run:\n  ${problems.join("\n  ")}\n  failed responses: ${failed.join(", ")}`);
  console.log(`first run: engine ready ${seconds(first.engineReady)}, first board ${seconds(first.board)}, ${requests.length} requests (${intercepted} answered from the fixture)`);

  // 3. A reload shows the cached report without asking Sleeper or GitHub anything.
  const before = intercepted;
  await page.reload({ waitUntil: "load" });
  await page.waitForSelector("#rosters .panel", { timeout: 60_000 });
  const cached = await page.evaluate(() => window.__smoke);
  if (cached.engineReady !== undefined) fail("the reload loaded the engine again");
  if (intercepted !== before) fail(`the reload made ${intercepted - before} Sleeper or GitHub requests`);
  if (!(await visible(page, team))) fail(`team "${team}" is not visible after the reload`);
  if (problems.length) fail(`errors on the reload:\n  ${problems.join("\n  ")}`);
  console.log(`reload: cached board ${seconds(cached.board)}, no Sleeper or GitHub requests`);

  // 3b. The same board on a phone-sized screen: the page does not scroll sideways, no name is cut off, one roster is on
  // screen under the bar that picks it, and the site's controls end the page instead of floating over it.
  await page.setViewport({ width: 390, height: 844 }); // no isMobile: changing it would reload the page
  const phone = await page.evaluate(() => {
    const shown = (n) => n.offsetParent !== null;
    return {
      sideways: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      cut: [...document.querySelectorAll(".nm, .lb, .il")].filter((n) => shown(n) && n.scrollWidth > n.clientWidth + 1).length,
      rosters: [...document.querySelectorAll("#rosters > .panel")].filter(shown).length,
      bar: shown(document.getElementById("rbar")),
      controls: getComputedStyle(document.querySelector(".site-controls")).position,
    };
  });
  if (process.env.SMOKE_SHOT_PHONE) await page.screenshot({ path: process.env.SMOKE_SHOT_PHONE, fullPage: true });
  if (phone.sideways > 0) fail(`the board scrolls sideways by ${phone.sideways}px on a phone`);
  if (phone.cut) fail(`${phone.cut} names are cut off on a phone`);
  if (phone.rosters !== 1 || !phone.bar) fail(`a phone shows ${phone.rosters} rosters (want 1) and the roster bar is ${phone.bar ? "there" : "missing"}`);
  if (phone.controls !== "static") fail(`the site's controls are ${phone.controls} on a phone`);
  await page.setViewport({ width: 800, height: 600 });
  console.log("phone: no sideways scroll, no cut-off names, one roster on screen");

  // 4. A league id that is not all digits gets the link back to the form; an unknown league says it was not found.
  await page.goto(`${ORIGIN}/board?league=NOPE1&team=x`, { waitUntil: "load" });
  await page.waitForSelector('#site-main a[href="/"]');
  if (await page.$(".site-progress")) fail("a league id that is not all digits started a report");
  await page.goto(`${ORIGIN}/board?league=${UNKNOWN}&team=x`, { waitUntil: "load" });
  await page.waitForSelector(".site-message", { timeout: 120_000 });
  const message = await page.$eval(".site-message", (n) => n.textContent);
  if (!/not found/i.test(message)) fail(`unknown league message: ${message}`);
  console.log(`unknown league: "${message}"`);
  console.log("smoke: PASS");
} catch (e) {
  const page = (await browser.pages()).at(-1);
  const shown = await page?.evaluate(() => document.body.innerText.slice(0, 2000)).catch(() => "(no page)");
  console.error(`page shows:\n${shown}\nproblems:\n  ${problems.join("\n  ")}\nfailed responses:\n  ${failed.join("\n  ")}\nrequests (${requests.length}):\n  ${requests.slice(-40).join("\n  ")}`);
  process.exitCode = 1;
  throw e;
} finally {
  await browser.close();
  cleanup();
}
