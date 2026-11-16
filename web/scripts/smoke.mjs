// Smoke test in a real browser: the built site under `wrangler dev`, headless Chrome, Sleeper and GitHub answered
// from the synthetic fixture. Not part of CI. Run `pnpm build` first, then `node scripts/smoke.mjs`.
//
//   SMOKE_PUPPETEER  folder holding puppeteer-core (default: the spike's node_modules)
//   SMOKE_CHROME     Chrome executable (default: the macOS install)
//   SMOKE_PORT       port for wrangler dev (default 8787)
//   SMOKE_SHOT       if set, a PNG path for a screenshot of the first board
import { spawn } from "node:child_process";
import { copyFileSync, existsSync, mkdirSync, readFileSync } from "node:fs";
import { createRequire } from "node:module";
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
const http = JSON.parse(readFileSync(join(fixture, "http.json"), "utf8"));
const expected = JSON.parse(readFileSync(join(fixture, "expected", "board-data.json"), "utf8"));
const INTERCEPTED = new Set(["api.sleeper.app", "raw.githubusercontent.com"]);
const ALLOWED = new Set([new URL(ORIGIN).host, ...INTERCEPTED, "fonts.googleapis.com", "fonts.gstatic.com"]);

function answer(url) {
  const asFixture = url.replaceAll(`/league/${ALIAS}`, `/league/${meta.league_id}`);
  const body = http[asFixture];
  return body === undefined ? undefined : body.replaceAll(JSON.stringify(meta.league_id), JSON.stringify(ALIAS));
}

const fail = (message) => {
  throw new Error(`smoke: ${message}`);
};

if (!existsSync(join(dist, "board.html"))) fail("no dist/board.html: run `pnpm build` first");
mkdirSync(join(dist, "data"), { recursive: true });
for (const name of ["players.json", "snapshot_index.json"]) copyFileSync(join(fixture, name), join(dist, "data", name));

const server = spawn("pnpm", ["exec", "wrangler", "dev", "--ip", "127.0.0.1", "--port", String(PORT)], {
  cwd: web,
  env: { ...process.env, WRANGLER_SEND_METRICS: "false" },
  stdio: ["ignore", "pipe", "pipe"],
});
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

const browser = await (async () => {
  await waitForServer();
  return puppeteer.launch({ executablePath: CHROME, headless: true, args: ["--no-first-run"] });
})().catch((e) => {
  server.kill();
  throw e;
});

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

  // 1. The form refuses a league id that is not all digits, then goes to the board for a valid one.
  await page.goto(`${ORIGIN}/`, { waitUntil: "load" });
  await page.type("#league", meta.league_id);
  await page.type("#team", meta.team);
  await page.click("button[type=submit]");
  await page.waitForSelector("#form-error:not([hidden])");
  if (new URL(page.url()).pathname !== "/") fail(`an invalid league id navigated to ${page.url()}`);
  await page.$eval("#league", (n) => (n.value = ""));
  await page.type("#league", ALIAS);
  await Promise.all([page.waitForNavigation(), page.click("button[type=submit]")]);
  const boardUrl = page.url();
  console.log(`form -> ${boardUrl.replace(ORIGIN, "")}`);

  // 2. Progress, then the board.
  await page.waitForSelector("#rosters .panel", { timeout: 120_000 });
  const first = await page.evaluate(() => window.__smoke);
  if (first.engineReady === undefined) fail(`the progress list never said the engine was ready: ${JSON.stringify(first.lines)}`);
  if (!(await visible(page, team))) fail(`team "${team}" is not visible on the board`);
  const title = await page.title();
  if (title !== `${expected.league} Trade Board`) fail(`title is "${title}"`);
  if (!(await page.$(".site-controls"))) fail("no site controls over the board");
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

  // 4. An unknown league says so.
  await page.goto(`${ORIGIN}/board?league=NOPE1&team=x`, { waitUntil: "load" });
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
  server.kill();
}
