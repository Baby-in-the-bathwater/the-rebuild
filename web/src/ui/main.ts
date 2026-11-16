// The site's one entry: index.html (the form) and board.html (the board) say which page they are on <body data-page>.
import "./site.css";
import { startForm } from "./form";

const storage = (() => {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
})();

if (document.body.dataset.page === "board") {
  // The board page brings the board's sources and the worker; the form page does not need them.
  void import("./board").then(({ startBoard }) => startBoard(document, window));
} else {
  startForm(document, { storage, navigate: (url) => window.location.assign(url) });
}
