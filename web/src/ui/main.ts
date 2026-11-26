// The site's one entry: index.html (the form) and board.html (the board) say which page they are on <body data-page>.
import "./site.css";
import { createSleeper } from "../data/sleeper";
import { findLeagues } from "../data/user";
import { warmEngine } from "../engine/warm";
import { startForm } from "./form";

const storage = (() => {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
})();

/** The board page's code did not load (a network error, or an old page asking for a chunk a deploy replaced) or
 * did not start: say so in place of "Building the trade board". */
function showLoadFailure(doc: Document): void {
  const main = doc.getElementById("site-main") ?? doc.body.appendChild(doc.createElement("main"));
  main.id = "site-main";
  main.className = "site-main";
  doc.body.className = "site-page";
  const title = doc.createElement("h1");
  title.className = "site-title";
  title.textContent = "The page did not load";
  const text = doc.createElement("p");
  text.className = "site-lede";
  text.textContent = "Part of this page could not be loaded. Check your connection, then reload.";
  const reload = doc.createElement("a");
  reload.className = "site-btn site-primary";
  reload.href = doc.location.pathname + doc.location.search;
  reload.textContent = "Reload";
  const actions = doc.createElement("p");
  actions.className = "site-actions";
  actions.append(reload);
  main.replaceChildren(title, text, actions);
}

if (document.body.dataset.page === "board") {
  // The board page brings the board's sources and the worker; the form page does not need them.
  import("./board")
    .then(({ startBoard }) => startBoard(document, window))
    .catch(() => showLoadFailure(document));
} else {
  const sleeper = createSleeper({ fetch: (input, init) => window.fetch(input, init) });
  startForm(document, {
    storage,
    navigate: (url) => window.location.assign(url),
    findLeagues: (username) => findLeagues(sleeper, username),
  });
  // Download the engine while the visitor types and picks, once the page itself has loaded, so the board page
  // finds it in the cache.
  const warm = () => void warmEngine((input, init) => window.fetch(input, init));
  if (document.readyState === "complete") warm();
  else window.addEventListener("load", warm, { once: true });
}
