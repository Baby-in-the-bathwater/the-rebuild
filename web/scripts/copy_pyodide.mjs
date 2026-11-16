// Copy the Pyodide runtime files the site needs from node_modules into public/pyodide/<version>/.
// The folder name carries the version, so the files can be cached forever (see public/_headers).
import { copyFileSync, mkdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const webRoot = dirname(dirname(fileURLToPath(import.meta.url)));
const src = join(webRoot, "node_modules", "pyodide");
const { version } = JSON.parse(readFileSync(join(src, "package.json"), "utf8"));
const out = join(webRoot, "public", "pyodide", version);
const FILES = ["pyodide.mjs", "pyodide.asm.mjs", "pyodide.asm.wasm", "python_stdlib.zip", "pyodide-lock.json"];

mkdirSync(out, { recursive: true });
for (const name of FILES) {
  copyFileSync(join(src, name), join(out, name));
  console.log(`${name}: ${statSync(join(out, name)).size} bytes`);
}
console.log(`-> ${out}`);
