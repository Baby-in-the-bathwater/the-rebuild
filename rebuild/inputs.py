"""Save an engine inputs dict to a folder and read it back, so a run can be recorded and replayed without the network.
The engine never imports this module: it belongs to the command line, which does the disk work.

Layout: meta.json (version, run_at, options, chain, benchmark_note, team), state.json, players.json, pull.json,
benchmark.json, history/<league id>.json, values.csv, snapshot_index.json (the index, or null), snapshots/<sha>.csv."""
import json
import os

VERSION = 1


def _write_json(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(value, f)


def _write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def save(inputs: dict, folder: str, team: str) -> None:
    """Write `inputs` and the team asked for into `folder`. The benchmark's `_path` (a local file path that
    `find_shipped` adds) is left out, and `inputs` is not changed."""
    bm = inputs["benchmark"]
    if isinstance(bm, dict):
        bm = {k: v for k, v in bm.items() if k != "_path"}
    _write_json(os.path.join(folder, "meta.json"), {
        "version": inputs["version"], "run_at": inputs["run_at"], "options": inputs["options"], "chain": inputs["chain"],
        "benchmark_note": inputs["benchmark_note"], "team": team})
    for key in ("state", "players", "pull"):
        _write_json(os.path.join(folder, key + ".json"), inputs[key])
    _write_json(os.path.join(folder, "benchmark.json"), bm)
    for lid, bundle in inputs["history"].items():
        _write_json(os.path.join(folder, "history", f"{lid}.json"), bundle)
    _write_text(os.path.join(folder, "values.csv"), inputs["values_csv"])
    _write_json(os.path.join(folder, "snapshot_index.json"), inputs["snapshot_index"])
    for sha, text in inputs["snapshots"].items():
        _write_text(os.path.join(folder, "snapshots", f"{sha}.csv"), text)


def _read(folder, name, as_json=True):
    path = os.path.join(folder, name)
    if not os.path.isfile(path):
        raise ValueError(f"replay folder {folder} is missing {name}")
    with open(path, encoding="utf-8", newline="") as f:
        return json.load(f) if as_json else f.read()


def _files(folder, sub, suffix):
    d = os.path.join(folder, sub)
    return sorted(n[:-len(suffix)] for n in os.listdir(d) if n.endswith(suffix)) if os.path.isdir(d) else []


def load(folder: str) -> tuple[dict, str]:
    """The inputs dict and the team recorded with it. Raises ValueError for a missing file or another version."""
    meta = _read(folder, "meta.json")
    if meta.get("version") != VERSION:
        raise ValueError(f"replay folder {folder} is version {meta.get('version')}, expected {VERSION}")
    inputs = {key: meta[key] for key in ("version", "run_at", "options", "chain", "benchmark_note")}
    for key in ("state", "players", "pull", "benchmark"):
        inputs[key] = _read(folder, key + ".json")
    inputs["history"] = {lid: _read(folder, f"history/{lid}.json") for lid in _files(folder, "history", ".json")}
    inputs["values_csv"] = _read(folder, "values.csv", as_json=False)
    inputs["snapshot_index"] = _read(folder, "snapshot_index.json")
    inputs["snapshots"] = {sha: _read(folder, f"snapshots/{sha}.csv", as_json=False) for sha in _files(folder, "snapshots", ".csv")}
    return inputs, meta["team"]
