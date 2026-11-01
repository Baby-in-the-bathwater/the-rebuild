"""Dynasty trade values from the DynastyProcess open data feed (MIT-licensed CSV, refreshed daily).

Players are matched on (position, normalized name). Picks are priced the way the feed prices them:
the current season's picks by exact slot when the draft is still ahead, next season's picks by
projected tier (Early / Mid / Late third of the draft order), the season after flat, and anything
further out discounted 15% per extra year."""
import csv
import io
import os
import re
import time
import unicodedata

import requests

URL = "https://raw.githubusercontent.com/dynastyprocess/data/master/files/values.csv"
ORD = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th", 5: "5th", 6: "6th", 7: "7th"}
FAR_YEAR_DISCOUNT = 0.85


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    s = s.lower().replace(".", "").replace("'", "")
    s = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", "", s)
    return re.sub(r"[^a-z]", "", s)


# Column names the feed used before April 2020 (historical snapshots), mapped onto today's. Those files carry no
# scrape_date and no PICK rows.
OLD_COLUMNS = {"mergename": "player", "1QBValue": "value_1qb", "2QBValue": "value_2qb", "2QB Value": "value_2qb"}


class Values:
    def __init__(self, rows, superflex):
        self.col = "value_2qb" if superflex else "value_1qb"
        self.superflex = superflex
        self.players = {}
        self.picks = {}
        self.asof = None
        for r in rows:
            if "player" not in r:
                r = {OLD_COLUMNS.get(k.strip("\ufeff "), k.strip("\ufeff ")): v for k, v in r.items() if k is not None}
            try:
                v = int(float(r[self.col]))
            except (ValueError, TypeError, KeyError):
                continue
            self.asof = self.asof or r.get("scrape_date")
            if r["pos"] == "PICK":
                self.picks[r["player"]] = v
            else:
                self.players[(r["pos"], norm(r["player"]))] = v

    @classmethod
    def load(cls, cache_dir, superflex, refresh=False, ttl=20 * 3600):
        os.makedirs(cache_dir, exist_ok=True)
        p = os.path.join(cache_dir, "dynastyprocess_values.csv")
        if refresh or not os.path.exists(p) or time.time() - os.path.getmtime(p) > ttl:
            r = requests.get(URL, timeout=60)
            r.raise_for_status()
            with open(p, "w", encoding="utf-8", newline="") as f:
                f.write(r.text)
        with open(p, encoding="utf-8") as f:
            rows = list(csv.DictReader(io.StringIO(f.read())))
        return cls(rows, superflex)

    def player(self, p):
        return self.players.get((p.get("position"), norm(p.get("full_name") or "")), 0)

    def tier(self, slot, n_teams):
        third = n_teams / 3.0
        return "Early" if slot <= third else ("Mid" if slot <= 2 * third else "Late")

    def pick(self, season, rnd, proj_slot, n_teams, cur_season, draft_pending):
        """Value of a pick. `proj_slot` is the original team's projected draft slot (1 = first pick)."""
        season = int(season)
        rn = ORD.get(rnd, f"{rnd}th")
        if season == cur_season:
            if not draft_pending:
                return 0
            exact = self.picks.get(f"{season} Pick {rnd}.{proj_slot:02d}")
            if exact is None:   # 2019 snapshots number the current draft's picks overall ("2019 Pick 13")
                exact = self.picks.get(f"{season} Pick {(rnd - 1) * n_teams + proj_slot}")
            if exact is not None:
                return exact
            return self.picks.get(f"{season} {self.tier(proj_slot, n_teams)} {rn}", self.picks.get(f"{season} {rn}", 0))
        nxt = cur_season + 1 if not draft_pending else cur_season
        if season == nxt:
            v = self.picks.get(f"{season} {self.tier(proj_slot, n_teams)} {rn}")
            if v is None:
                v = self.picks.get(f"{season} {rn}", 0)
            return v
        flat_season = nxt + 1
        base = self.picks.get(f"{flat_season} {rn}")
        if base is None:
            base = self.picks.get(f"{nxt} {rn}", 0)
        years_out = season - flat_season
        return int(base * (FAR_YEAR_DISCOUNT ** max(0, years_out)))
