# Team 3: rebuild brief

Synthetic Dynasty League (Sleeper L1), 2026 season, week 6. Format: 12-team Superflex dynasty, 0.5 PPR, 4.0-pt pass TD, 3-round rookie draft, 4 playoff teams, trade deadline week 11. Values: DynastyProcess value_2qb as of 2026-11-16. Manager: Manager 3.

## The call: rebuild

Sell the production that will not survive to 2028, buy first-round picks in the 2027 and 2028 drafts and players under 25, and plan on contending in 2028.

- thin depth (18th percentile) on a roster ranked 12th in total value
- core age 23.6: young enough that the rebuild should be short
- asset base ranks 12th of 12 (players + picks)

## Where the team stands

| | Team 3 | Rank of 12 | Pool percentile |
|-|-|-|-|
| Record | 3-3 | 7 | |
| Points per week | 146.7 | 11 | 16 |
| QB points per week | 23.6 (z -2.30) | | 2 |
| RB points per week | 30.3 (z -1.36) | | 9 |
| WR points per week | 66.0 (z +1.23) | | 87 |
| TE points per week | 20.8 (z +1.42) | | 89 |
| Startable depth, produced for this team so far (QB/RB/WR/TE) | 9 (1/2/4/2) | 8 | 18 |
| Startable on the roster today, by season ppg wherever they played (QB/RB/WR/TE) | 10 (1/2/5/2) | | |
| Starter age (weighted by starts) | 25.7 | | 11 (higher = older) |
| Lineup efficiency | 97% | | 19 |
| QB in the Superflex | 100% of weeks | | 34 |
| Player value | 26,061 | 10 | |
| Pick value | 11,982 | 12 | |
| Core age (top-8 assets) | 23.6 | 1 (1 = youngest) | |
| First-round picks held | 2027: 1, 2028: 0, 2029: 1 | | |

Pool percentile is this team's within-league z-score placed against every team-season in the benchmark pool, so it reads the same in any league of this format. The first depth line is what this roster has actually produced, week by week, including missed weeks as zeros; a player acquired mid-season counts from the week he arrived, which is how the pool is measured. The second line is the roster as it stands today, each player scored on his season average over games played, wherever he played.

## What wins this format

Benchmark: dynasty-12team-sf-halfppr, 1121 league-seasons and 13452 team-seasons across 2018 to 2026 (shipped benchmark built 2026-10-31; run with --pool to crawl a fresh one).

Win% standard deviations gained per one-SD positional edge, pooled: RB +0.58, WR +0.43, QB +0.37, TE +0.18 (R² 0.70). Ordering by season:

| Season | Teams | QB | RB | WR | TE | R² | r(depth) | r(age) |
|-|-|-|-|-|-|-|-|-|
| 2018 | 12 | +0.20 | +0.74 | +0.24 | +0.23 | 0.82 | +0.70 | -0.24 |
| 2019 | 240 | +0.41 | +0.57 | +0.42 | +0.15 | 0.59 | +0.66 | -0.05 |
| 2020 | 516 | +0.41 | +0.54 | +0.44 | +0.17 | 0.65 | +0.61 | +0.12 |
| 2021 | 936 | +0.39 | +0.52 | +0.46 | +0.20 | 0.70 | +0.68 | +0.26 |
| 2022 | 1476 | +0.40 | +0.55 | +0.39 | +0.17 | 0.71 | +0.68 | +0.34 |
| 2023 | 2016 | +0.40 | +0.50 | +0.47 | +0.18 | 0.73 | +0.73 | +0.33 |
| 2024 | 2412 | +0.36 | +0.67 | +0.42 | +0.19 | 0.72 | +0.70 | +0.25 |
| 2025 | 2832 | +0.36 | +0.63 | +0.43 | +0.18 | 0.72 | +0.71 | +0.23 |
| 2026 | 3012 | +0.34 | +0.55 | +0.44 | +0.17 | 0.67 | +0.68 | +0.24 |

Champions versus the field (861 champions in 10440 completed team-seasons):

| Metric | Champion mean z | Champion raw | Field raw |
|-|-|-|-|
| ppg | +1.06 | 140.60 | 123.01 |
| QB | +0.56 | 37.23 | 33.09 |
| RB | +0.73 | 42.06 | 33.42 |
| WR | +0.42 | 43.00 | 39.06 |
| TE | +0.10 | 10.38 | 10.08 |
| depth | +0.90 | 9.43 | 7.07 |
| depRB | +0.69 | 3.14 | 2.21 |
| depWR | +0.54 | 3.10 | 2.37 |
| depQB | +0.51 | 1.99 | 1.51 |
| sf_qb_rate | +0.35 | 0.90 | 0.83 |
| starter_age | +0.21 | 26.81 | 26.52 |

Position that carried the champion (largest positional z): RB 320 (37%), WR 243 (28%), QB 190 (22%), TE 108 (13%).

Startable depth and outcomes, completed seasons:

| Startable players | Teams | Win% | Playoff rate | Title rate |
|-|-|-|-|-|
| 0-4 | 1848 | 26% | 5% | 0.3% |
| 5-6 | 2563 | 43% | 29% | 2.9% |
| 7-8 | 2897 | 55% | 60% | 7.5% |
| 9-10 | 2009 | 63% | 80% | 14.8% |
| 11-+ | 1123 | 71% | 91% | 23.7% |

Superflex usage: QB in the Superflex under half the weeks n=883 win 30%, playoffs 16%; half to most weeks n=6444 win 49%, playoffs 47%; every week n=3113 win 57%, playoffs 65%.

| Starter age | Teams | Win% | Playoff rate | Title rate |
|-|-|-|-|-|
| under 25 | 1293 | 38% | 25% | 4.6% |
| 25 to 26 | 2479 | 47% | 43% | 6.9% |
| 26 to 27 | 3011 | 51% | 53% | 9.0% |
| 27 to 28 | 2277 | 55% | 60% | 9.3% |
| 28 and up | 1380 | 56% | 61% | 10.7% |

Correlation of starter age with win% (within-league z): +0.26. Older rosters win now; this is the trade-off the rebuild timeline prices.

## This league's history

| Season | Champion | Record | Carried by | Champ depth | This roster: finish, record, manager | Depth |
|-|-|-|-|-|-|-|
| 2025 | Manager 8 | 86% | RB | 11 | 12th of 12, 0%, Manager 3 | 8 |
| 2026 | in season | | | | 7th of 12, 50%, Manager 3 | 9 |

Roster ids persist when a Sleeper league renews, so the right-hand columns are this roster slot's history under whoever managed it.

## Sell, hold, keep

| Sell | Pos | Age | PPG | Value | Why |
|-|-|-|-|-|-|
| Player Zac | RB | 23 | 15.9 | 2,968 | RB age 23, producing 15.9 ppg: peak sale window, a contender pays now |
| Player Ric | WR | 29 | 12.1 | 1,962 | WR age 29: past the 27 turn in this format's value curve; IR (knee, out for the season) now, so selling before the deadline is selling low |
| Player Kec | RB | 23 | 14.4 | 1,920 | RB age 23, producing 14.4 ppg: peak sale window, a contender pays now |
| Player Bed | QB | 29 | 15.0 | 1,364 | QB age 29, producing 15.0 ppg: peak sale window, a contender pays now |
| Player Fac | TE | 28 | 11.2 | 1,022 | TE age 28: past the 28 turn in this format's value curve |

**Player Ric is out now** (IR: knee, out for the season). Contenders need points before the playoffs and Sleeper gives no return date, so his deals go to retooling teams, which are building for next season and can wait on him; expect them to pay less than a healthy price. 3 two-team deals below; 2 three-team deals route him to one with a third team's help. The other path: hold him past the week 11 deadline and sell after the season to next year's contenders, once he is healthy.

**Hold** (young enough to be here when the window opens): Player Koc (WR, 21, 3,393), Player Zoc (WR, 22, 3,109), Player Zob (WR, 24, 2,705), Player Bib (TE, 25, 1,702), Player Meb (QB, 22, 1,450), Player Ced (QB, 22, 1,278).

**Keep as cheap youth** (roster at no cost, cut only for a better one): Player Qec (RB, 22), Player Vac (RB, 21).

## Deals, ranked

### 1. Player Zac to Team 5 (needs RB)

You send: Player Zac (RB, 23) (2,968)

| Variant | Package | Value | Return |
|-|-|-|-|
| Ask | 2027 R1 (1.12) (3,315), Player Pub (TE, 21) (387) | 3,702 | 125% |
| Target | Player Zec (RB, 22) (1,637), Player Fad (WR, 22) (1,499) | 3,136 | 106% |
| Floor | Player Fad (WR, 22) (1,499), Player Pec (TE, 23) (1,123) | 2,622 | 88% |

Walk away if the Player Zec (RB, 22) is not in it, or the return falls under 2,611.

### 2. Player Zac to Team 1 (needs RB)

You send: Player Zac (RB, 23) (2,968)

| Variant | Package | Value | Return |
|-|-|-|-|
| Ask | Player Tic (TE, 22) (568), Player Nib (WR, 25) (2,864) | 3,432 | 116% |
| Target | Player Xeb (RB, 22) (2,068), Player Hab (TE, 22) (954) | 3,022 | 102% |
| Floor | Player Xeb (RB, 22) (2,068), Player Tic (TE, 22) (568) | 2,636 | 89% |

Walk away if the Player Xeb (RB, 22) is not in it, or the return falls under 2,611.

### 3. Player Zac to Team 6 (needs RB)

You send: Player Zac (RB, 23) (2,968)

| Variant | Package | Value | Return |
|-|-|-|-|
| Ask | Player Dic (RB, 21) (2,355), Player Rad (TE, 23) (1,348) | 3,703 | 125% |
| Target | Player Dic (RB, 21) (2,355), Player Sic (WR, 23) (718) | 3,073 | 104% |
| Floor | Player Dic (RB, 21) (2,355), Player Qic (RB, 23) (336) | 2,691 | 91% |

Walk away if the Player Dic (RB, 21) is not in it, or the return falls under 2,611.

### 4. Player Zac to Team 12 (needs RB)

You send: Player Zac (RB, 23) (2,968)

| Variant | Package | Value | Return |
|-|-|-|-|
| Ask | Player Voc (WR, 23) (2,516), Player Fuc (WR, 21) (1,004) | 3,520 | 119% |
| Target | Player Voc (WR, 23) (2,516), Player Cab (RB, 23) (427) | 2,943 | 99% |
| Floor | Player Fic (WR, 22) (1,595), Player Fuc (WR, 21) (1,004) | 2,599 | 88% |

Walk away if the Player Voc (WR, 23) is not in it, or the return falls under 2,611.

### 5. Player Ric to Team 10 (needs WR) (injured: a retooling team's buy-low)

You send: Player Ric (WR, 29) (1,962)

| Variant | Package | Value | Return |
|-|-|-|-|
| Ask | Player Feb (WR, 23) (922), 2027 R2 (1,275) | 2,197 | 112% |
| Target | Player Feb (WR, 23) (922), 2028 R2 (1,083) | 2,005 | 102% |
| Floor | Player Suc (WR, 21) (420), 2027 R2 (1,275) | 1,695 | 86% |

Walk away if the Player Feb (WR, 23) is not in it, or the return falls under 1,726.

### 6. Player Ric to Team 5 (injured: a retooling team's buy-low)

You send: Player Ric (WR, 29) (1,962)

| Variant | Package | Value | Return |
|-|-|-|-|
| Ask | Player Pec (TE, 23) (1,123), 2028 R2 (1,083) | 2,206 | 112% |
| Target | Player Pec (TE, 23) (1,123), 2029 R2 (920) | 2,043 | 104% |
| Floor | Player Pec (TE, 23) (1,123), Player Hed (WR, 23) (729) | 1,852 | 94% |

Walk away if the Player Pec (TE, 23) is not in it, or the return falls under 1,726.

### 7. Player Ric to Team 1 (injured: a retooling team's buy-low)

You send: Player Ric (WR, 29) (1,962)

| Variant | Package | Value | Return |
|-|-|-|-|
| Ask | Player Hab (TE, 22) (954), 2027 R2 (1,275) | 2,229 | 114% |
| Target | Player Hab (TE, 22) (954), 2028 R2 (1,083) | 2,037 | 104% |
| Floor | Player Tic (TE, 22) (568), 2027 R2 (1,275) | 1,843 | 94% |

Walk away if the Player Hab (TE, 22) is not in it, or the return falls under 1,726.

### 8. Player Kec to Team 6 (needs RB)

You send: Player Kec (RB, 23) (1,920)

| Variant | Package | Value | Return |
|-|-|-|-|
| Ask | Player Rad (TE, 23) (1,348), Player Muc (RB, 23) (874) | 2,222 | 116% |
| Target | Player Rad (TE, 23) (1,348), Player Sic (WR, 23) (718) | 2,066 | 108% |
| Floor | Player Rad (TE, 23) (1,348), Player Qic (RB, 23) (336) | 1,684 | 88% |

Walk away if the Player Rad (TE, 23) is not in it, or the return falls under 1,689.

### 9. Player Kec to Team 12 (needs RB)

You send: Player Kec (RB, 23) (1,920)

| Variant | Package | Value | Return |
|-|-|-|-|
| Ask | Player Fic (WR, 22) (1,595), Player Fuc (WR, 21) (1,004) | 2,599 | 135% |
| Target | Player Fic (WR, 22) (1,595), Player Cab (RB, 23) (427) | 2,022 | 105% |
| Floor | Player Fic (WR, 22) (1,595), Player Cub (TE, 21) (201) | 1,796 | 94% |

Walk away if the Player Fic (WR, 22) is not in it, or the return falls under 1,689.

### 10. Player Kec to Team 11 (needs RB)

You send: Player Kec (RB, 23) (1,920)

| Variant | Package | Value | Return |
|-|-|-|-|
| Ask | Player Gob (RB, 23) (1,675), Player Tob (WR, 22) (533) | 2,208 | 115% |
| Target | Player Gob (RB, 23) (1,675), Player Duc (RB, 21) (258) | 1,933 | 101% |
| Floor | Player Hub (QB, 22) (1,190), Player Tob (WR, 22) (533) | 1,723 | 90% |

Walk away if the Player Gob (RB, 23) is not in it, or the return falls under 1,689.

### 11. Player Kec to Team 5 (needs RB)

You send: Player Kec (RB, 23) (1,920)

| Variant | Package | Value | Return |
|-|-|-|-|
| Ask | Player Fad (WR, 22) (1,499), Player Hed (WR, 23) (729) | 2,228 | 116% |
| Target | Player Fad (WR, 22) (1,499), Player Pub (TE, 21) (387) | 1,886 | 98% |
| Floor | Player Hed (WR, 23) (729), 2027 R2 (956) | 1,685 | 88% |

Walk away if the Player Fad (WR, 22) is not in it, or the return falls under 1,689.

### 12. Player Bed to Team 1

You send: Player Bed (QB, 29) (1,364)

| Variant | Package | Value | Return |
|-|-|-|-|
| Ask | Player Hab (TE, 22) (954), Player Tic (TE, 22) (568) | 1,522 | 112% |
| Target | Player Hab (TE, 22) (954), Player Tic (TE, 22) (568) | 1,522 | 112% |
| Floor | Player Wuc (RB, 22) (178), 2028 R2 (1,083) | 1,261 | 92% |

Walk away if the Player Hab (TE, 22) is not in it, or the return falls under 1,200.

7 more deals, ranked below these, are on the trade board (All deals view).

## Three-team deals

When a buyer cannot pay in what you want, a third team takes the buyer's players you do not want and pays you instead. Each is kept only if both other teams land between 87% and 115% of what they send, at market value. Open them on the trade board to adjust.

### T1. Player Zac to Team 12, with Team 1

Team 12 can cover 54% of Player Zac in what you want. Team 1 pays the rest for Player Zib, Player Wad, filling its RB hole. Beats the best two-team package from Team 12.

| Team | Gets | Value | Sends | Return |
|-|-|-|-|-|
| Team 3 | Player Fic (WR, 22) from Team 12, Player Hab (TE, 22) from Team 1, Player Tic (TE, 22) from Team 1 | 3,117 | 2,968 | 105% |
| Team 12 | Player Zac (RB, 23) from Team 3 | 2,968 | 3,132 | 95% |
| Team 1 | Player Zib (RB, 28) from Team 12, Player Wad (QB, 28) from Team 12 | 1,537 | 1,522 | 101% |

### T2. Player Kec to Team 1, with Team 4

Team 1 can cover 79% of Player Kec in what you want. Team 4 pays the rest for Player Lec, Player Seb, filling its TE/WR hole. Beats the best two-team package from Team 1.

| Team | Gets | Value | Sends | Return |
|-|-|-|-|-|
| Team 3 | Player Hab (TE, 22) from Team 1, Player Tic (TE, 22) from Team 1, Player Xac (WR, 21) from Team 4 | 2,085 | 1,920 | 109% |
| Team 1 | Player Kec (RB, 23) from Team 3 | 1,920 | 2,069 | 93% |
| Team 4 | Player Lec (TE, 31) from Team 1, Player Seb (WR, 27) from Team 1 | 547 | 563 | 97% |

### T3. Player Ric to Team 10, with Team 1

Team 10 can cover 21% of Player Ric in what you want. Team 1 pays the rest for Player Zic, Player Tib, filling its RB/TE hole. Beats the best two-team package from Team 10. Player Ric is out now (IR): Team 10 is retooling and can wait on him.

| Team | Gets | Value | Sends | Return |
|-|-|-|-|-|
| Team 3 | Player Suc (WR, 21) from Team 10, Player Hab (TE, 22) from Team 1, Player Tic (TE, 22) from Team 1 | 1,942 | 1,962 | 99% |
| Team 10 | Player Ric (WR, 29) from Team 3 | 1,962 | 1,924 | 102% |
| Team 1 | Player Zic (RB, 27) from Team 10, Player Tib (TE, 29) from Team 10 | 1,504 | 1,522 | 99% |

### T4. Player Zac to Team 11, with Team 1

Team 11 can cover 49% of Player Zac in what you want. Team 1 pays the rest for Player Bad, filling its TE hole. Beats the best two-team package from Team 11.

| Team | Gets | Value | Sends | Return |
|-|-|-|-|-|
| Team 3 | Player Hub (QB, 22) from Team 11, Player Duc (RB, 21) from Team 11, Player Hab (TE, 22) from Team 1, Player Tic (TE, 22) from Team 1 | 2,970 | 2,968 | 100% |
| Team 11 | Player Zac (RB, 23) from Team 3 | 2,968 | 2,976 | 100% |
| Team 1 | Player Bad (TE, 28) from Team 11 | 1,528 | 1,522 | 100% |

### T5. Player Ric to Team 1, with Team 4

Team 1 can cover 78% of Player Ric in what you want. Team 4 pays the rest for Player Seb, Player Lec, filling its TE/WR hole. Beats the best two-team package from Team 1. Player Ric is out now (IR): Team 1 is retooling and can wait on him.

| Team | Gets | Value | Sends | Return |
|-|-|-|-|-|
| Team 3 | Player Hab (TE, 22) from Team 1, Player Tic (TE, 22) from Team 1, Player Xac (WR, 21) from Team 4 | 2,085 | 1,962 | 106% |
| Team 1 | Player Ric (WR, 29) from Team 3 | 1,962 | 2,069 | 95% |
| Team 4 | Player Seb (WR, 27) from Team 1, Player Lec (TE, 31) from Team 1 | 547 | 563 | 97% |

### T6. Player Kec to Team 4, with Team 5

Team 4 can cover 81% of Player Kec in what you want. Team 5 pays the rest for Player Kab, filling its RB hole. Beats the best two-team package from Team 4.

| Team | Gets | Value | Sends | Return |
|-|-|-|-|-|
| Team 3 | Player Hob (TE, 22) from Team 4, Player Pub (TE, 21) from Team 5 | 1,951 | 1,920 | 102% |
| Team 4 | Player Kec (RB, 23) from Team 3 | 1,920 | 1,989 | 97% |
| Team 5 | Player Kab (RB, 30) from Team 4 | 425 | 387 | 110% |

### T7. Player Bed to Team 12, with Team 10

Team 12 can cover 31% of Player Bed in what you want. Team 10 pays the rest for Player Wad, filling its QB hole. Beats the best two-team package from Team 12.

| Team | Gets | Value | Sends | Return |
|-|-|-|-|-|
| Team 3 | Player Cab (RB, 23) from Team 12, Player Feb (WR, 23) from Team 10 | 1,349 | 1,364 | 99% |
| Team 12 | Player Bed (QB, 29) from Team 3 | 1,364 | 1,449 | 94% |
| Team 10 | Player Wad (QB, 28) from Team 12 | 1,022 | 922 | 111% |

### T8. Player Bed to Team 4, with Team 5

Team 4 can cover 74% of Player Bed in what you want. Team 5 pays the rest for Player Kab, filling its RB hole. Beats the best two-team package from Team 4.

| Team | Gets | Value | Sends | Return |
|-|-|-|-|-|
| Team 3 | Player Had (QB, 22) from Team 4, Player Pub (TE, 21) from Team 5 | 1,401 | 1,364 | 103% |
| Team 4 | Player Bed (QB, 29) from Team 3 | 1,364 | 1,439 | 95% |
| Team 5 | Player Kab (RB, 30) from Team 4 | 425 | 387 | 110% |

## What to expect: rebuilds in this format

Bottom-3 teams in a completed season, followed for three seasons (2610 cases). Columns: win% / mean finish / playoff rate; title rate in years 1, 2, 3.

| Group | Cases | Year 1 | Year 2 | Year 3 | Title % |
|-|-|-|-|-|-|
| All bottom-3 teams | 2610 | 38% / 8.4 / 26% | 45% / 7.2 / 41% | 51% / 6.4 / 51% | 3.1% / 5.4% / 7.1% |
| Same manager kept the team | 2244 | 38% / 8.3 / 27% | 47% / 7.0 / 43% | 52% / 6.2 / 53% | 3.3% / 5.8% / 7.4% |
| New manager took it over (orphan) | 366 | 34% / 8.9 / 21% | 36% / 8.5 / 24% | 43% / 7.5 / 33% | 1.9% / 2.6% / 5.0% |
| Behaviour late-N through N+1: sold for picks | 1219 | 30% / 9.5 / 13% | 41% / 7.9 / 32% | 49% / 6.6 / 48% | 1.4% / 4.7% / 6.8% |
| Behaviour late-N through N+1: bought (sent picks) | 654 | 49% / 6.6 / 48% | 53% / 5.9 / 58% | 55% / 5.8 / 59% | 6.9% / 8.0% / 8.5% |
| Behaviour late-N through N+1: churned (no net picks) | 468 | 40% / 8.0 / 31% | 46% / 7.2 / 41% | 49% / 6.6 / 47% | 3.6% / 4.5% / 7.2% |
| Behaviour late-N through N+1: stood pat | 269 | 38% / 8.5 / 23% | 42% / 7.8 / 35% | 47% / 7.0 / 44% | 1.1% / 2.6% / 3.3% |
| Net +2 or more first-round picks acquired | 500 | 27% / 9.9 / 9% | 40% / 8.1 / 30% | 51% / 6.4 / 46% | 1.2% / 4.9% / 10.7% |
| Got younger (sent players 2+ years older than received) | 665 | 30% / 9.5 / 15% | 40% / 8.1 / 29% | 45% / 7.3 / 39% | 1.7% / 3.2% / 4.9% |
| Got older (received players 2+ years older than sent) | 305 | 48% / 6.8 / 47% | 51% / 6.2 / 53% | 57% / 5.4 / 63% | 7.2% / 6.9% / 7.6% |
| 6+ trades | 985 | 38% / 8.3 / 29% | 47% / 7.0 / 44% | 53% / 6.0 / 54% | 4.3% / 6.8% / 9.8% |
| 1 to 2 trades | 610 | 39% / 8.3 / 28% | 45% / 7.4 / 39% | 48% / 6.8 / 45% | 2.0% / 3.4% / 4.2% |

Behaviour measured before the next season starts only (so every outcome column is a genuine forecast):

| Group | Cases | Year 1 | Year 2 | Year 3 | Title % |
|-|-|-|-|-|-|
| Pre-season: sold for picks | 1075 | 33% / 9.1 / 19% | 43% / 7.5 / 37% | 51% / 6.3 / 51% | 2.5% / 5.2% / 7.6% |
| Pre-season: bought (sent picks) | 601 | 46% / 7.2 / 40% | 51% / 6.4 / 51% | 53% / 6.1 / 56% | 5.8% / 6.5% / 7.9% |
| Pre-season: churned (no net picks) | 552 | 38% / 8.3 / 27% | 44% / 7.4 / 37% | 48% / 6.7 / 45% | 2.9% / 5.8% / 7.8% |
| Pre-season: stood pat | 382 | 38% / 8.5 / 23% | 44% / 7.4 / 38% | 46% / 7.0 / 47% | 1.0% / 2.9% / 2.1% |
| Pre-season: net +2 or more 1sts | 381 | 28% / 9.6 / 14% | 42% / 7.7 / 33% | 52% / 6.3 / 47% | 2.1% / 6.5% / 10.8% |
| Pre-season: net +1 1st | 443 | 35% / 8.8 / 24% | 44% / 7.4 / 39% | 51% / 6.3 / 53% | 3.4% / 5.5% / 7.8% |
| Pre-season: 4+ trades | 1137 | 38% / 8.4 / 27% | 46% / 7.0 / 43% | 53% / 6.1 / 54% | 3.7% / 6.6% / 8.7% |

Orphan takeovers:

| Group | Cases | Year 1 | Year 2 | Year 3 | Title % |
|-|-|-|-|-|-|
| Orphan: sold for picks | 197 | 25% / 10.0 / 8% | 34% / 8.9 / 22% | 42% / 7.7 / 31% | 0.5% / 1.3% / 7.4% |
| Orphan: bought (sent picks) | 84 | 47% / 6.8 / 51% | 43% / 7.6 / 35% | 46% / 7.1 / 38% | 6.0% / 6.3% / 0.0% |
| Orphan: churned (no net picks) | 64 | 40% / 8.3 / 23% | 38% / 8.3 / 24% | 42% / 7.8 / 26% | 1.6% / 2.2% / 3.7% |
| Orphan: stood pat | 21 | 35% / 8.6 / 19% | 34% / 9.6 / 0% | 46% / 6.8 / 50% | 0.0% / 0.0% / 0.0% |
| Orphan: 6+ trades | 159 | 30% / 9.2 / 20% | 36% / 8.4 / 27% | 44% / 7.4 / 31% | 1.9% / 4.8% / 6.3% |
| Orphan: 0 to 2 trades | 104 | 35% / 8.8 / 19% | 34% / 9.1 / 11% | 33% / 8.7 / 22% | 0.0% / 0.0% / 0.0% |
| Orphan: inherited starters under 26 | 141 | 36% / 8.5 / 26% | 39% / 8.0 / 31% | 50% / 6.5 / 40% | 0.7% / 4.9% / 5.6% |
| Orphan: inherited starters 27+ | 125 | 29% / 9.6 / 14% | 33% / 9.2 / 17% | 35% / 8.8 / 21% | 1.6% / 0.0% / 5.2% |

Regression of year-2 win% on the starting state and behaviour (n=1902, R² 0.14): starter age -0.038 per year, orphan takeover -0.079, net firsts acquired -0.010 each, trades +0.004 each, year-N depth +0.009 per player. Low R² means the moves set the odds, not the outcome.

## Rookie pick hit rates in this format

32472 rookie-draft picks, classes 2019 to 2025. Startable = averaged the position threshold in a season; top-24 / top-12 = finished that high at the position by ppg, any of the first three seasons.

| Slot | Picks | Startable yr 1 | Startable in 3 | Top-24 in 3 | Top-12 in 3 | QB | RB | WR | TE |
|-|-|-|-|-|-|-|-|-|-|
| early 1st | 2697 | 79% | 96% | 73% | 49% | 35% | 34% | 25% | 1% |
| mid 1st | 2696 | 70% | 87% | 68% | 37% | 23% | 25% | 43% | 7% |
| late 1st | 2704 | 63% | 81% | 59% | 29% | 15% | 29% | 42% | 14% |
| round 2 | 8096 | 25% | 49% | 31% | 12% | 14% | 28% | 46% | 10% |
| round 3 | 8029 | 10% | 33% | 19% | 9% | 10% | 36% | 36% | 15% |

Top-24 at the position within three years, by position and slot:

| Position | early 1st | mid 1st | late 1st | round 2 | round 3 |
|-|-|-|-|-|-|
| QB | 77% (n=955) | 57% (n=614) | 43% (n=414) | 40% (n=1171) | 20% (n=827) |
| RB | 76% (n=906) | 85% (n=664) | 46% (n=774) | 32% (n=2273) | 25% (n=2910) |
| WR | 61% (n=680) | 59% (n=1146) | 62% (n=1129) | 20% (n=3762) | 10% (n=2930) |
| TE | 96% (n=26) | 98% (n=192) | 96% (n=371) | 67% (n=789) | 26% (n=1201) |

## Caveats

- Values are one public market (DynastyProcess). Your league's managers price things their own way; the ask / target / floor ladder is where to start, not where to end.
- Projected pick slots come from today's standings; they move every week until the season ends.
- Packages are built from what each counterparty actually holds, scored by what a team in your mode should want. They are openers. The counterparty's needs column tells you which one to lead with.
- The benchmark describes the format, not your league. The league-history section is the local check.

Generated by the-rebuild (https://github.com/Baby-in-the-bathwater/the-rebuild). Data: Sleeper public API, DynastyProcess values.