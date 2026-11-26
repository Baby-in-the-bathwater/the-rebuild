import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { webRoot } from "../testing/fixture";
import { PYODIDE_VERSION } from "./python";
import { engineFiles, WARM_PYODIDE_VERSION, warmEngine } from "./warm";

describe("warmEngine", () => {
  it("uses the Pyodide version the engine loads", () => {
    expect(WARM_PYODIDE_VERSION).toBe(PYODIDE_VERSION);
  });

  it("lists the engine bundle and every Pyodide file the build copies", () => {
    const script = readFileSync(join(webRoot, "scripts", "copy_pyodide.mjs"), "utf8");
    const copied = /const FILES = (\[[^\]]+\])/.exec(script)![1]!;
    const names = JSON.parse(copied) as string[];
    expect(engineFiles("1.2.3").sort()).toEqual([...names.map((n) => `/pyodide/1.2.3/${n}`), "/engine/engine.zip"].sort());
  });

  it("requests each file once and never rejects, even when a request fails", async () => {
    const asked: string[] = [];
    const fake = (async (input: RequestInfo | URL) => {
      asked.push(String(input));
      if (String(input).endsWith(".wasm")) throw new TypeError("offline");
      return new Response("x");
    }) as typeof fetch;
    await expect(warmEngine(fake)).resolves.toBeUndefined();
    expect(asked.sort()).toEqual(engineFiles().sort());
  });
});
