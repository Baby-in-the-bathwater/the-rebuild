export type EngineRequest = { id: number; type: "ping" };

export type EngineResponse =
  | { id: number; type: "pong"; engine: string }
  | { id: number; type: "error"; message: string };

export const ENGINE_NAME = "placeholder";

export function handle(req: EngineRequest): EngineResponse {
  switch (req.type) {
    case "ping":
      return { id: req.id, type: "pong", engine: ENGINE_NAME };
    default: {
      const unknown = req as { id: number; type: string };
      return { id: unknown.id, type: "error", message: `unknown message type: ${unknown.type}` };
    }
  }
}
