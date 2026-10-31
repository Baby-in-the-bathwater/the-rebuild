"""The written brief (Markdown): the call, where the team stands, what wins the format, league history, the ledger, deals, what to expect."""
import statistics as st

from .trades import buy_positions
from .metrics import TH, team_rows, zwithin


def pc(x, d=0):
    return "-" if x is None else f"{x * 100:.{d}f}%"


def num(x, d=2):
    return "-" if x is None else f"{x:+.{d}f}" if d else f"{x:,.0f}"


def call_text(g, league, bm, assets=None):
    me = g["team"]
    mode = g["mode"]
    if mode == "rebuild":
        return (f"Sell the production that will not survive to {g['window']}, buy first-round picks in the {league.pick_seasons[0]} and {league.pick_seasons[1]} drafts "
                f"and players under 25, and plan on contending in {g['window']}.")
    if mode == "contend":
        return (f"The window is open now. Spend far-out picks and non-producing youth on an older producer at your weakest starting spot and hold everything that scores.")
    weak = " or ".join(buy_positions(g, me, league)) or "the weakest spot"
    nxt = league.pick_seasons[0]
    own_first = any(pk["round"] == 1 and pk["own"] and pk["season"] == nxt for pk in me["picks"])
    keep = f"Keep the producers and your own {nxt} first" if own_first else "Keep the producers"
    if assets is not None and not assets["sell"]:
        return (f"Neither window is open, and nothing on the roster is past its sell age. {keep}; "
                f"spend the other picks on one young starter at {weak} so the team is a contender in {g['window']}.")
    return (f"Neither window is open. Sell what is past its sell age while a contender still pays. {keep}, "
            f"and buy one young starter at {weak} so the team is a contender in {g['window']}.")


def lineage_table(bundles, chain, pdb, rid, league):
    rows = []
    for lid in reversed(chain):
        b = bundles.get(lid)
        if not b or not b.get("matchups"):
            continue
        rs = zwithin(team_rows(b, pdb))
        if not rs:
            continue
        names = {u["user_id"]: (u.get("display_name") or u.get("username")) for u in b.get("users") or []}
        srt = sorted(rs, key=lambda x: (-x["winpct"], -x["ppg"]))
        rk = {x["rid"]: i + 1 for i, x in enumerate(srt)}
        ch = next((r for r in rs if r["champ"]), None)
        mine = next((r for r in rs if r["rid"] == rid), None)
        carried = max(("QB", "RB", "WR", "TE"), key=lambda m: ch.get("z_" + m) or -9) if ch else None
        rows.append({"season": b["league"]["season"], "status": b["league"]["status"], "champion": names.get(ch["owner"]) if ch else None,
                     "champ_win": ch["winpct"] if ch else None, "carried": carried, "champ_depth": ch["depth"] if ch else None,
                     "my_rank": rk.get(rid) if mine else None, "my_win": mine["winpct"] if mine else None, "my_owner": names.get(mine["owner"]) if mine else None,
                     "my_depth": mine["depth"] if mine else None})
    return rows


def write(path, league, values, g, assets, deals, bm, lineage, shipped_note):
    me = g["team"]
    row = g["row"] or {}
    pct = g["pct"]
    n = g["n"]
    L = []
    A = L.append
    A(f"# {me['name']}: {g['mode']} brief")
    A("")
    A(f"{league.lg.get('name')} (Sleeper {league.id}), {league.season} season, week {league.week}. Format: {league.n}-team {'Superflex' if league.fmt['superflex'] else '1QB'} "
      f"{'dynasty' if league.fmt['dynasty'] else 'league'}, {league.fmt['rec']} PPR, {league.fmt['pass_td']}-pt pass TD{', TE premium' if league.fmt['te_prem'] else ''}, "
      f"{league.rounds}-round rookie draft, {league.playoff_teams} playoff teams{f', trade deadline week {league.trade_deadline}' if league.trade_deadline else ''}. "
      f"Values: DynastyProcess {values.col} as of {values.asof}. Manager: {me['owner']}.")
    A("")
    A(f"## The call: {g['mode']}")
    A("")
    A(call_text(g, league, bm, assets))
    A("")
    for r in g["reasons"]:
        A(f"- {r}")
    A("")
    A("## Where the team stands")
    A("")
    A(f"| | {me['name']} | Rank of {n} | Pool percentile |")
    A("|-|-|-|-|")
    A(f"| Record | {me['wins']}-{me['losses']} | {me['rank']} | |")
    if row:
        A(f"| Points per week | {row['ppg']:.1f} | {sorted((-r['ppg'], r['rid']) for r in g['rows']).index((-row['ppg'], me['rid'])) + 1} | {pct.get('ppg', '-')} |")
        for m in ("QB", "RB", "WR", "TE"):
            A(f"| {m} points per week | {row[m]:.1f} (z {row.get('z_' + m, 0):+.2f}) | | {pct.get(m, '-')} |")
        A(f"| Startable depth, produced for this team so far (QB/RB/WR/TE) | {row['depth']} ({row['depQB']}/{row['depRB']}/{row['depWR']}/{row['depTE']}) | {g['ledger_rank']['startable']} | {pct.get('depth', '-')} |")
        now = {pos: sum(1 for p in me["players"] if p["pos"] == pos and p["startable"]) for pos in ("QB", "RB", "WR", "TE")}
        A(f"| Startable on the roster today, by season ppg wherever they played (QB/RB/WR/TE) | {sum(now.values())} ({now['QB']}/{now['RB']}/{now['WR']}/{now['TE']}) | | |")
        if row.get("starter_age"):
            A(f"| Starter age (weighted by starts) | {row['starter_age']:.1f} | | {pct.get('starter_age', '-')} (higher = older) |")
        A(f"| Lineup efficiency | {row['eff'] * 100:.0f}% | | {pct.get('eff', '-')} |")
        if league.fmt["superflex"]:
            A(f"| QB in the Superflex | {row['sf_qb_rate'] * 100:.0f}% of weeks | | {pct.get('sf_qb_rate', '-')} |")
    A(f"| Player value | {me['player_value']:,} | {g['ledger_rank']['player_value']} | |")
    A(f"| Pick value | {me['pick_value']:,} | {g['ledger_rank']['pick_value']} | |")
    if me["core_age"]:
        A(f"| Core age (top-8 assets) | {me['core_age']:.1f} | {g['ledger_rank']['core_age']} (1 = youngest) | |")
    A(f"| First-round picks held | " + ", ".join(f"{s}: {c}" for s, c in me["firsts"].items()) + " | | |")
    A("")
    A("Pool percentile is this team's within-league z-score placed against every team-season in the benchmark pool, so it reads the same in any league of this format. "
      "The first depth line is what this roster has actually produced, week by week, including missed weeks as zeros; a player acquired mid-season counts from the week he arrived, "
      "which is how the pool is measured. The second line is the roster as it stands today, each player scored on his season average over games played, wherever he played.")
    A("")
    # what wins
    A("## What wins this format")
    A("")
    if bm:
        A(f"Benchmark: {bm['label']}, {bm['league_seasons']} league-seasons and {bm['team_seasons']} team-seasons across {min(bm['seasons'])} to {max(bm['seasons'])}{shipped_note}.")
        A("")
        cp = bm["coef_pooled"]["coef"]
        order = sorted(("QB", "RB", "WR", "TE"), key=lambda m: -cp.get(m, 0))
        A(f"Win% standard deviations gained per one-SD positional edge, pooled: " + ", ".join(f"{m} {cp.get(m, 0):+.2f}" for m in order) + f" (R² {bm['coef_pooled']['r2']:.2f}). Ordering by season:")
        A("")
        A("| Season | Teams | QB | RB | WR | TE | R² | r(depth) | r(age) |")
        A("|-|-|-|-|-|-|-|-|-|")
        for s, c in bm["coef_by_season"].items():
            A(f"| {s} | {c['n']} | {c['coef'].get('QB', 0):+.2f} | {c['coef'].get('RB', 0):+.2f} | {c['coef'].get('WR', 0):+.2f} | {c['coef'].get('TE', 0):+.2f} | {c['r2']:.2f} | {c['corr'].get('depth', 0):+.2f} | {c['corr'].get('starter_age') or 0:+.2f} |")
        A("")
        ch = bm["champions"]
        prof = ch["profile"]
        A(f"Champions versus the field ({ch['n']} champions in {ch['field']} completed team-seasons):")
        A("")
        A("| Metric | Champion mean z | Champion raw | Field raw |")
        A("|-|-|-|-|")
        for m in ("ppg", "QB", "RB", "WR", "TE", "depth", "depRB", "depWR", "depQB", "sf_qb_rate", "starter_age"):
            if m == "sf_qb_rate" and not league.fmt["superflex"]:
                continue
            p = prof[m]
            A(f"| {m} | {num(p['champ_z'])} | {p['champ_raw']:.2f} | {p['field_raw']:.2f} |" if p["champ_raw"] is not None else f"| {m} | - | - | - |")
        A("")
        cb = ch["carried_by"]
        A("Position that carried the champion (largest positional z): " + ", ".join(f"{k} {v} ({v / max(1, ch['n']) * 100:.0f}%)" for k, v in sorted(cb.items(), key=lambda x: -x[1])) + ".")
        A("")
        A("Startable depth and outcomes, completed seasons:")
        A("")
        A("| Startable players | Teams | Win% | Playoff rate | Title rate |")
        A("|-|-|-|-|-|")
        for b in bm["depth_buckets"]:
            A(f"| {b['lo']}-{b['hi'] - 1 if b['hi'] < 99 else '+'} | {b['n']} | {pc(b['win'])} | {pc(b['playoff'])} | {pc(b['champ'], 1)} |")
        A("")
        if league.fmt["superflex"] and bm.get("sf_qb_buckets"):
            A("Superflex usage: " + "; ".join(f"{b['label']} n={b['n']} win {pc(b['win'])}, playoffs {pc(b['playoff'])}" for b in bm["sf_qb_buckets"]) + ".")
            A("")
        A("| Starter age | Teams | Win% | Playoff rate | Title rate |")
        A("|-|-|-|-|-|")
        for b in bm["age_buckets"]:
            A(f"| {b['label']} | {b['n']} | {pc(b['win'])} | {pc(b['playoff'])} | {pc(b['champ'], 1)} |")
        A("")
        A(f"Correlation of starter age with win% (within-league z): {num(bm.get('age_corr'))}. Older rosters win now; this is the trade-off the rebuild timeline prices.")
        A("")
    else:
        A("No benchmark pool was built for this format (run with --pool to crawl one).")
        A("")
    # league history
    A("## This league's history")
    A("")
    if lineage:
        A(f"| Season | Champion | Record | Carried by | Champ depth | This roster: finish, record, manager | Depth |")
        A("|-|-|-|-|-|-|-|")
        for r in lineage:
            mine = f"{r['my_rank']}th of {n}, {pc(r['my_win'])}, {r['my_owner']}" if r["my_rank"] else "-"
            if r["status"] != "complete":
                A(f"| {r['season']} | in season | | | | {mine} | {r['my_depth'] if r['my_depth'] is not None else '-'} |")
            else:
                A(f"| {r['season']} | {r['champion'] or '-'} | {pc(r['champ_win'])} | {r['carried'] or '-'} | {r['champ_depth'] if r['champ_depth'] is not None else '-'} | {mine} | {r['my_depth'] if r['my_depth'] is not None else '-'} |")
        A("")
        A("Roster ids persist when a Sleeper league renews, so the right-hand columns are this roster slot's history under whoever managed it.")
    else:
        A("No prior seasons found (no previous_league_id on this league).")
    A("")
    # ledger
    A("## Sell, hold, keep")
    A("")
    if assets["sell"]:
        A("| Sell | Pos | Age | PPG | Value | Why |")
        A("|-|-|-|-|-|-|")
        for p in assets["sell"]:
            A(f"| {p['name']} | {p['pos']} | {p['age']} | {p['ppg']} | {p['value']:,} | {assets['reason'].get(p['id'], '')} |")
        A("")
    else:
        A("Nothing on the roster clears the sell bar (value 900+ at an age a contender still pays for).")
        A("")
    if assets["hold"]:
        A("**Hold** (young enough to be here when the window opens): " + ", ".join(f"{p['name']} ({p['pos']}, {p['age']}, {p['value']:,})" for p in assets["hold"]) + ".")
        A("")
    if assets["keep"]:
        A("**Keep as cheap youth** (roster at no cost, cut only for a better one): " + ", ".join(f"{p['name']} ({p['pos']}, {p['age']})" for p in assets["keep"]) + ".")
        A("")
    # deals
    A("## Deals, ranked")
    A("")
    if not deals:
        A("No deal clears the floor with any counterparty right now. Re-run after the next waiver cycle or widen the counterparties.")
        A("")
    for i, d in enumerate(deals, 1):
        fixed = d.get("sends") or d.get("receives")
        A(f"### {i}. {d['title']}")
        A("")
        A(("You send: " if d.get("sends") else "You receive: ") + ", ".join(f"{x['label']} ({x['value']:,})" for x in fixed))
        A("")
        A("| Variant | Package | Value | Return |")
        A("|-|-|-|-|")
        base = sum(x["value"] for x in fixed)
        for name in d["vars"]:
            v = d["vars"].get(name)
            if not v:
                continue
            ratio = (v["value"] / base) if d.get("sends") else (base / v["value"] if v["value"] else 0)
            A(f"| {name} | " + ", ".join(f"{x['label']} ({x['value']:,})" for x in v["items"]) + f" | {v['value']:,} | {ratio * 100:.0f}% |")
        A("")
        A(f"Walk away if {d['walk']}.")
        A("")
    # expectations
    if bm and g["mode"] != "contend":
        tr = bm["trajectories"]
        A("## What to expect: rebuilds in this format")
        A("")
        A(f"Bottom-3 teams in a completed season, followed for three seasons ({tr['cases']} cases). Columns: win% / mean finish / playoff rate; title rate in years 1, 2, 3.")
        A("")
        A("| Group | Cases | Year 1 | Year 2 | Year 3 | Title % |")
        A("|-|-|-|-|-|-|")

        def line(r):
            def cell(h):
                return f"{pc(r['win' + h])} / {r['rank' + h]:.1f} / {pc(r['po' + h])}" if r.get("win" + h) is not None else "-"
            return f"| {r['group']} | {r['n']} | {cell('1')} | {cell('2')} | {cell('3')} | {pc(r['champ1'], 1)} / {pc(r['champ2'], 1)} / {pc(r['champ3'], 1)} |"
        for r in tr["main"]:
            A(line(r))
        A("")
        A("Behaviour measured before the next season starts only (so every outcome column is a genuine forecast):")
        A("")
        A("| Group | Cases | Year 1 | Year 2 | Year 3 | Title % |")
        A("|-|-|-|-|-|-|")
        for r in tr["pre"]:
            A(line(r))
        A("")
        A("Orphan takeovers:")
        A("")
        A("| Group | Cases | Year 1 | Year 2 | Year 3 | Title % |")
        A("|-|-|-|-|-|-|")
        for r in tr["orphan"]:
            A(line(r))
        A("")
        o = tr["ols_n2"]
        if o["n"]:
            c = o["coef"]
            A(f"Regression of year-2 win% on the starting state and behaviour (n={o['n']}, R² {o['r2']:.2f}): starter age {c['age_n']:+.3f} per year, orphan takeover {c['orphan']:+.3f}, "
              f"net firsts acquired {c['r1_net']:+.3f} each, trades {c['trades']:+.3f} each, year-N depth {c['depth_n']:+.3f} per player. Low R² means the moves set the odds, not the outcome.")
            A("")
    if bm:
        pk = bm["picks"]
        A("## Rookie pick hit rates in this format")
        A("")
        A(f"{pk['n']} rookie-draft picks, classes {pk['classes'][0] if pk['classes'] else '-'} to {pk['classes'][-1] if pk['classes'] else '-'}. "
          "Startable = averaged the position threshold in a season; top-24 / top-12 = finished that high at the position by ppg, any of the first three seasons.")
        A("")
        A("| Slot | Picks | Startable yr 1 | Startable in 3 | Top-24 in 3 | Top-12 in 3 | QB | RB | WR | TE |")
        A("|-|-|-|-|-|-|-|-|-|-|")
        for r in pk["table"]:
            A(f"| {r['slot']} | {r['n']} | {pc(r['startable1'])} | {pc(r['startable3'])} | {pc(r['top24_3'])} | {pc(r['top12_3'])} | {pc(r['share_QB'])} | {pc(r['share_RB'])} | {pc(r['share_WR'])} | {pc(r['share_TE'])} |")
        A("")
        A("Top-24 at the position within three years, by position and slot:")
        A("")
        A("| Position | early 1st | mid 1st | late 1st | round 2 | round 3 |")
        A("|-|-|-|-|-|-|")
        for p_, cells in pk["by_pos"]["top24_3"].items():
            A(f"| {p_} | " + " | ".join(f"{pc(c['rate'])} (n={c['n']})" if c["n"] else "-" for c in cells.values()) + " |")
        A("")
    A("## Caveats")
    A("")
    A("- Values are one public market (DynastyProcess). Your league's managers price things their own way; the ask / target / floor ladder is where to start, not where to end.")
    A("- Projected pick slots come from today's standings; they move every week until the season ends.")
    A("- Packages are built from what each counterparty actually holds, scored by what a team in your mode should want. They are openers. The counterparty's needs column tells you which one to lead with.")
    A("- The benchmark describes the format, not your league. The league-history section is the local check.")
    A("")
    A("Generated by the-rebuild (https://github.com/Baby-in-the-bathwater/the-rebuild). Data: Sleeper public API, DynastyProcess values.")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    return path
