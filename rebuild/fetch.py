"""Every network and disk-cache read the engine needs: the league pull from Sleeper, today's DynastyProcess values
feed, and the feed's weekly history (the commit index and one CSV per commit). The engine modules take what these
return as plain data."""
import json
import os
import time

import requests

from .league import league_pull  # noqa: F401  (moved to league.py; kept here for old imports)

VALUES_URL = "https://raw.githubusercontent.com/dynastyprocess/data/master/files/values.csv"
COMMITS_URL = "https://api.github.com/repos/dynastyprocess/data/commits"
RAW_URL = "https://raw.githubusercontent.com/dynastyprocess/data/{sha}/files/values.csv"


# ------------------------------------------------------------------ DynastyProcess
def values_csv(cache_dir, refresh=False, ttl=20 * 3600):
    """Today's values feed as CSV text, downloaded at most once per `ttl`."""
    os.makedirs(cache_dir, exist_ok=True)
    p = os.path.join(cache_dir, "dynastyprocess_values.csv")
    if refresh or not os.path.exists(p) or time.time() - os.path.getmtime(p) > ttl:
        r = requests.get(VALUES_URL, timeout=60)
        r.raise_for_status()
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(r.text)
    with open(p, encoding="utf-8") as f:
        return f.read()


def snapshot_index(cache_dir, ttl=6 * 24 * 3600):
    """[(iso date, sha)] for every values.csv commit, oldest first. Cached for most of a week."""
    d = os.path.join(cache_dir, "dp_history")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "commits.json")
    if os.path.exists(p) and time.time() - os.path.getmtime(p) < ttl:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")   # the Actions runner's token: its shared IP hits the anonymous limit often
    if token:
        headers["Authorization"] = f"Bearer {token}"
    out, page = [], 1
    while True:
        r = requests.get(COMMITS_URL, params={"path": "files/values.csv", "per_page": 100, "page": page}, timeout=30,
                         headers=headers)
        r.raise_for_status()
        batch = r.json()
        out += [(c["commit"]["committer"]["date"], c["sha"]) for c in batch]
        if len(batch) < 100:
            break
        page += 1
    out.sort()
    with open(p, "w", encoding="utf-8") as f:
        json.dump(out, f)
    return out


def snapshot_csv(cache_dir, sha):
    """One historical values.csv as text. Each commit is immutable, so it is downloaded once and kept."""
    d = os.path.join(cache_dir, "dp_history")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, f"{sha}.csv")
    if not os.path.exists(p):
        r = requests.get(RAW_URL.format(sha=sha), timeout=60)
        r.raise_for_status()
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(r.text)
    with open(p, encoding="utf-8") as f:
        return f.read()
