"""Thin Sleeper API client: retries, 429 back-off, and a JSON disk cache for the big static pulls."""
import json
import os
import threading
import time

import requests

BASE = "https://api.sleeper.app/v1"
_lock = threading.Lock()


class Sleeper:
    def __init__(self, cache_dir, players_ttl=24 * 3600):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self.s = requests.Session()
        self.s.headers["User-Agent"] = "the-rebuild/1.0 (+https://github.com/Baby-in-the-bathwater/the-rebuild)"
        self.players_ttl = players_ttl
        self.calls = 0
        self._players = None

    # ------------------------------------------------------------------ transport
    def get(self, path, retries=4):
        url = path if path.startswith("http") else f"{BASE}/{path}"
        for i in range(retries):
            try:
                r = self.s.get(url, timeout=30)
                with _lock:
                    self.calls += 1
                if r.status_code == 429:
                    time.sleep(5 + 5 * i)
                    continue
                if r.status_code == 404:
                    return None
                r.raise_for_status()
                return r.json()
            except requests.RequestException:
                if i == retries - 1:
                    return None
                time.sleep(1 + i)
        return None

    def cached(self, key, ttl, fn):
        p = os.path.join(self.cache_dir, key + ".json")
        if os.path.exists(p) and time.time() - os.path.getmtime(p) < ttl:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        data = fn()
        if data is not None:
            with open(p, "w", encoding="utf-8") as f:
                json.dump(data, f)
        return data

    # ------------------------------------------------------------------ endpoints
    def players(self):
        if self._players is None:
            self._players = self.cached("players_nfl", self.players_ttl, lambda: self.get("players/nfl")) or {}
        return self._players

    def state(self):
        return self.get("state/nfl") or {}

    def league(self, lid):
        return self.get(f"league/{lid}")

    def rosters(self, lid):
        return self.get(f"league/{lid}/rosters") or []

    def users(self, lid):
        return self.get(f"league/{lid}/users") or []

    def traded_picks(self, lid):
        return self.get(f"league/{lid}/traded_picks") or []

    def matchups(self, lid, week):
        return self.get(f"league/{lid}/matchups/{week}") or []

    def transactions(self, lid, week):
        return self.get(f"league/{lid}/transactions/{week}") or []

    def winners_bracket(self, lid):
        return self.get(f"league/{lid}/winners_bracket") or []

    def drafts(self, lid):
        return self.get(f"league/{lid}/drafts") or []

    def draft_picks(self, draft_id):
        return self.get(f"draft/{draft_id}/picks") or []

    def user_leagues(self, uid, season):
        return self.get(f"user/{uid}/leagues/nfl/{season}") or []

    def user(self, name_or_id):
        return self.get(f"user/{name_or_id}")


def position(pdb, pid):
    """Position for a player id; team defenses are alphabetic ids with no players-db row."""
    p = pdb.get(pid)
    if p and p.get("position"):
        return p["position"]
    return "DEF" if str(pid).isalpha() else "?"
