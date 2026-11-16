import { expect, test } from "vitest";
import { handle } from "./protocol";

test("ping answers pong with the engine name", () => {
  expect(handle({ id: 7, type: "ping" })).toEqual({ id: 7, type: "pong", engine: "placeholder" });
});

test("an unknown message type gets an error reply", () => {
  expect(handle({ id: 8, type: "nope" } as never)).toEqual({
    id: 8,
    type: "error",
    message: "unknown message type: nope",
  });
});
