"""Write the two shared data files the site serves: a trimmed copy of Sleeper's player table and the index of past
DynastyProcess value snapshots.

    python3 web/scripts/build_data.py [--out web/public/data] [--players-from FILE] [--index-from FILE]

players.json: Sleeper's players/nfl, keyed by player id in Sleeper's order, each record cut to PLAYER_FIELDS (the full
table is about 10 MB; the engine reads a dozen fields).
snapshot_index.json: [[iso date, sha], ...] oldest first, the same data rebuild.fetch.snapshot_index returns. GITHUB_TOKEN
is used when set (the Actions runner's shared address hits the anonymous limit often).

If anything fails, or the new player table has fewer than MIN_PLAYERS players, or fewer than 80% of the players already
in the output folder, the existing files are left alone (or none are written) and the exit code is 1. Standard library only: the deploy job needs no pip install."""
import argparse
import json
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PLAYERS_URL = "https://api.sleeper.app/v1/players/nfl"
COMMITS_URL = "https://api.github.com/repos/dynastyprocess/data/commits"   # as rebuild/fetch.py
USER_AGENT = "the-rebuild/1.0 (+https://github.com/Baby-in-the-bathwater/the-rebuild)"   # as rebuild/sleeper.py
KEEP_RATIO = 0.8
MIN_PLAYERS = 5000   # Sleeper's table has well over 10,000; a fresh build (CI has no old file) still needs a floor

# Derived by searching the modules the browser loads (the files web/scripts/build_engine.py zips) for reads of a player
# record: league.pdb / League.player(), and the `pdb.get(pid)` reads in metrics, trade_history and grade. Re-derive it when
# one of them reads another field. The synthetic table does not carry every one of these, so the search is the authority.
PLAYER_FIELDS = (
    "age",                 # grade.team_rows (League.player)
    "birth_date",          # metrics.age_at; trade_history.age_on
    "fantasy_positions",   # trade_history.ppos, pval
    "first_name",          # trade_history.pname (name when full_name is missing)
    "full_name",           # League.player, grade, values.player, trade_history.pname
    "injury_body_part",    # grade.team_rows (inj_note)
    "injury_notes",        # grade.team_rows (inj_note)
    "injury_status",       # grade.team_rows (inj, out)
    "last_name",           # League.player, trade_history.pname
    "position",            # league.position, League.player, values.player, trade_history
    "team",                # grade.team_rows
    "years_exp",           # grade.team_rows; metrics.rookie_in
)


class DataError(Exception):
    pass


def trim(players):
    """The table with only PLAYER_FIELDS in each record, ids and fields in their original order."""
    keep = set(PLAYER_FIELDS)
    return {pid: ({k: v for k, v in rec.items() if k in keep} if isinstance(rec, dict) else rec) for pid, rec in players.items()}


def _get(url, params=None, headers=None, timeout=120):
    if params:
        url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def load_players(source=None):
    """Sleeper's player table, from a file when `source` is given."""
    if source:
        with open(source, encoding="utf-8") as f:
            players = json.load(f)
    else:
        players = _get(PLAYERS_URL)
    if not isinstance(players, dict) or not players:
        raise DataError("the player table is empty or not an object")
    return players


def load_index(source=None):
    """[[iso date, sha], ...] oldest first."""
    if source:
        with open(source, encoding="utf-8") as f:
            out = [list(x) for x in json.load(f)]
    else:
        headers = {"Accept": "application/vnd.github+json"}
        if os.environ.get("GITHUB_TOKEN"):
            headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
        out, page = [], 1
        while True:
            batch = _get(COMMITS_URL, {"path": "files/values.csv", "per_page": 100, "page": page}, headers, 30)
            out += [[c["commit"]["committer"]["date"], c["sha"]] for c in batch]
            if len(batch) < 100:
                break
            page += 1
    out.sort()
    if not out:
        raise DataError("the snapshot index is empty")
    return out


def _existing(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _write(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        json.dump(obj, f, separators=(",", ":"), ensure_ascii=False)
    os.replace(tmp, path)


def build(out_dir, players_from=None, index_from=None):
    """Write both files, or raise DataError and change nothing."""
    players_path = os.path.join(out_dir, "players.json")
    index_path = os.path.join(out_dir, "snapshot_index.json")
    try:
        players = trim(load_players(players_from))
        index = load_index(index_from)
    except DataError:
        raise
    except Exception as e:   # network, JSON, file: one failure kind for the caller
        raise DataError(f"download failed: {type(e).__name__}: {e}") from e
    if len(players) < MIN_PLAYERS:
        raise DataError(f"the new player table has {len(players)} players, under the floor of {MIN_PLAYERS}: writing nothing")
    old = _existing(players_path)
    if isinstance(old, dict) and len(players) < KEEP_RATIO * len(old):
        raise DataError(f"the new player table has {len(players)} players against {len(old)} in {players_path}: "
                        f"fewer than {int(KEEP_RATIO * 100)}%, keeping the old file")
    os.makedirs(out_dir, exist_ok=True)
    _write(players_path, players)
    _write(index_path, index)
    return len(players), len(index)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "web", "public", "data"))
    ap.add_argument("--players-from", help="read the player table from this file instead of Sleeper")
    ap.add_argument("--index-from", help="read the snapshot index from this file instead of GitHub")
    a = ap.parse_args(argv)
    try:
        n, m = build(a.out, a.players_from, a.index_from)
    except DataError as e:
        print(f"build_data: {e}", file=sys.stderr)
        return 1
    print(f"{n} players, {m} snapshots -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
