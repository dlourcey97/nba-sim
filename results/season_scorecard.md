# NBA Sim Season Scorecard — 2026-27

Graded from `prediction_history` after finals. No sportsbook lines or odds.

## Season to date

| Metric | Value |
| --- | ---: |
| Games graded | 14 |
| Winner accuracy | 71.4% |
| Spread MAE (margin) | 15.11 |
| Total MAE | 15.14 |
| Player MIN MAE | 9.04 |
| Player PTS MAE | 6.92 |
| 10–90 coverage (player stats) | 64.0% |
| Top confident picks hit rate | 33.3% (3/9) |
| Top picks avg claimed confidence | 77.1% |

## Notes

- 2026-10-20: no Top confident picks.
- 2026-10-21: claimed conf 77.1% vs hit rate 33.3% (3/9).
- Bakeoff: naive_last10 MIN 6.25 > Step F on 6.78 > off 6.88 > v1.0 7.63.
- 10-21 MIN: played MAE 9.92 (n=254); proj≥8 DNP MAE 20.21 (n=29). Top DNPs: Patrick Williams, Jahmai Mashack, Will Riley.

## 2026-10-20

| Metric | Value |
| --- | ---: |
| Games graded | 3 |
| Winner accuracy | 66.7% |
| Spread MAE | 7.83 |
| Total MAE | 17.00 |
| MIN MAE | 5.76 |
| PTS MAE | 5.76 |
| REB MAE | 2.71 |
| AST MAE | 1.61 |
| 10–90 coverage | 69.1% |
| Top confident picks | n/a (none produced) |

### Games

| Matchup | Pred winner | Actual | Hit | Pred score | Actual score | Pred margin | Act margin | Pred total | Act total |
| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: |
| BOS@DET | DET (55%) | DET | Y | BOS 114 – DET 117 | BOS 113 – DET 121 | +4.5 | +8.0 | 231.0 | 234.0 |
| PHI@NYK | NYK (69%) | PHI | N | PHI 114 – NYK 125 | PHI 106 – NYK 100 | +11.0 | -6.0 | 238.0 | 206.0 |
| OKC@SAS | OKC (63%) | OKC | Y | OKC 121 – SAS 114 | OKC 116 – SAS 104 | -9.0 | -12.0 | 236.0 | 220.0 |

### Player grades (MIN / PTS / REB / AST / STL / BLK)

| Player | Team | MIN pred/act | PTS | REB | AST | STL | BLK | in 10–90 (any miss listed) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Paul George | BOS | 31.9/31 | 21.0/38 | 7.0/5 | 4.0/3 | 2.0/5 | 0.0/0 | PTS,STL |
| Shai Gilgeous-Alexander | OKC | 35.0/36 | 31.0/32 | 6.0/6 | 7.0/4 | 1.0/3 | 0.0/3 | BLK |
| Tyrese Maxey | PHI | 33.4/40 | 22.0/28 | 5.0/4 | 7.0/5 | 2.0/3 | 0.0/3 | BLK |
| Stephon Castle | SAS | 30.8/28 | 19.0/24 | 6.0/7 | 7.0/1 | 1.0/0 | 0.0/0 | AST |
| Cade Cunningham | DET | 40.7/35 | 33.0/22 | 9.0/4 | 12.0/8 | 1.0/1 | 0.0/1 | MIN,REB |
| Jalen Duren | DET | 34.3/28 | 25.0/22 | 20.0/9 | 3.0/1 | 1.0/1 | 1.0/1 | MIN,REB |
| Jalen Brunson | NYK | 36.9/34 | 31.0/21 | 5.0/5 | 8.0/3 | 1.0/0 | 0.0/0 | AST |
| Duncan Robinson | DET | 32.0/28 | 17.0/21 | 4.0/2 | 3.0/2 | 1.0/1 | 0.0/0 | all |
| Jared McCain | OKC | 25.3/22 | 12.0/20 | 3.0/2 | 2.0/2 | 0.0/1 | 0.0/0 | all |
| Karl-Anthony Towns | NYK | 30.5/24 | 29.0/19 | 18.0/12 | 4.0/1 | 1.0/1 | 0.0/2 | all |
| Jaylen Brown | PHI | 29.2/35 | 20.0/19 | 7.0/8 | 5.0/6 | 1.0/1 | 0.0/1 | all |
| Javonte Green | DET | 7.3/18 | 0.0/19 | 0.0/4 | 0.0/0 | 0.0/0 | 0.0/0 | MIN,PTS,REB |
| Dylan Harper | SAS | 22.3/32 | 4.0/18 | 2.0/7 | 1.0/5 | 0.0/0 | 0.0/0 | MIN,PTS |
| Derrick White | BOS | 38.9/36 | 24.0/17 | 7.0/1 | 6.0/8 | 1.0/1 | 1.0/0 | REB |
| Payton Pritchard | BOS | 37.8/28 | 19.0/17 | 6.0/4 | 5.0/1 | 1.0/0 | 0.0/0 | MIN,AST |
| Josh Hart | NYK | 35.3/30 | 17.0/14 | 14.0/7 | 7.0/3 | 1.0/1 | 0.0/1 | REB |
| LeBron James | PHI | 31.2/34 | 22.0/14 | 9.0/9 | 9.0/7 | 1.0/1 | 0.0/1 | all |
| De'Aaron Fox | SAS | 35.1/32 | 22.0/14 | 6.0/7 | 7.0/7 | 1.0/1 | 0.0/0 | all |
| Chet Holmgren | OKC | 29.0/31 | 21.0/14 | 13.0/7 | 2.0/2 | 1.0/0 | 2.0/4 | all |
| Joel Embiid | PHI | 29.4/33 | 22.0/13 | 9.0/11 | 4.0/6 | 0.0/2 | 1.0/3 | BLK |
| Anfernee Simons | PHI | 7.8/25 | 0.0/13 | 0.0/2 | 0.0/0 | 0.0/0 | 0.0/0 | MIN,PTS,REB |
| Jayson Tatum | BOS | 38.6/38 | 28.0/13 | 11.0/4 | 6.0/11 | 1.0/0 | 0.0/0 | PTS,REB,AST |
| Andre Drummond | NYK | 0.0/24 | 0.0/12 | 0.0/14 | 0.0/4 | 0.0/1 | 0.0/2 | MIN,PTS,REB,AST,STL,BLK |
| Victor Wembanyama | SAS | 36.1/34 | 31.0/12 | 17.0/13 | 4.0/3 | 1.0/1 | 3.0/6 | PTS |
| Jalen Williams | OKC | 24.1/30 | 15.0/12 | 5.0/7 | 4.0/2 | 1.0/1 | 0.0/1 | all |
| Ausar Thompson | DET | 36.2/33 | 16.0/11 | 11.0/11 | 4.0/5 | 3.0/1 | 1.0/0 | all |
| Sam Hauser | BOS | 26.0/18 | 8.0/11 | 4.0/4 | 1.0/1 | 0.0/0 | 0.0/0 | MIN |
| OG Anunoby | NYK | 36.6/32 | 21.0/10 | 7.0/5 | 2.0/0 | 2.0/1 | 1.0/1 | PTS,AST |
| Kentavious Caldwell-Pope | PHI | 9.4/26 | 0.0/10 | 0.0/4 | 0.0/1 | 0.0/0 | 0.0/1 | MIN,PTS,REB,AST,BLK |
| Keldon Johnson | SAS | 14.8/20 | 0.0/10 | 0.0/4 | 0.0/1 | 0.0/2 | 0.0/0 | MIN,PTS,REB,STL |
| VJ Edgecombe | PHI | 32.9/35 | 13.0/9 | 7.0/4 | 4.5/1 | 1.0/1 | 0.0/0 | AST |
| Alex Caruso | OKC | 28.8/25 | 11.0/9 | 5.0/6 | 4.0/1 | 2.0/1 | 0.0/0 | all |
| Jose Alvarado | NYK | 14.1/16 | 0.0/8 | 0.0/3 | 0.0/3 | 0.0/2 | 0.0/0 | PTS,REB,AST,STL |
| Julian Champagnie | SAS | 29.8/30 | 10.0/8 | 6.0/3 | 2.0/1 | 1.0/2 | 0.0/3 | BLK |
| Isaiah Joe | DET | 0.0/19 | 0.0/8 | 0.0/2 | 0.0/2 | 0.0/1 | 0.0/1 | MIN,PTS,REB,AST,STL,BLK |
| Baylor Scheierman | BOS | 10.6/18 | 0.0/8 | 0.0/3 | 0.0/0 | 0.0/1 | 0.0/0 | MIN,PTS,REB,STL |
| Devin Vassell | SAS | 35.8/31 | 17.0/7 | 6.0/3 | 3.0/1 | 1.0/0 | 0.0/0 | MIN,PTS |
| Aday Mara | OKC | 0.0/12 | 0.0/7 | 0.0/2 | 0.0/1 | 0.0/0 | 0.0/1 | MIN,PTS,REB,AST,BLK |
| Cason Wallace | OKC | 24.2/19 | 5.0/6 | 3.0/3 | 2.0/2 | 1.0/1 | 0.0/0 | all |
| John Collins | DET | 13.0/25 | 0.0/6 | 0.0/5 | 0.0/1 | 0.0/1 | 0.0/1 | MIN |
| Paul Reed | DET | 10.7/17 | 0.0/6 | 0.0/6 | 0.0/2 | 0.0/1 | 0.0/0 | PTS,REB,AST,STL |
| Landry Shamet | NYK | 17.0/25 | 0.0/5 | 0.0/2 | 0.0/4 | 0.0/0 | 0.0/0 | MIN,AST |
| Jaylin Williams | OKC | 16.2/17 | 0.0/5 | 0.0/4 | 0.0/1 | 0.0/0 | 0.0/0 | all |
| Mikal Bridges | NYK | 36.0/33 | 19.0/4 | 5.0/3 | 4.0/1 | 1.0/0 | 0.0/1 | PTS,AST |
| Jordan Clarkson | NYK | 7.5/8 | 0.0/4 | 0.0/1 | 0.0/1 | 0.0/0 | 0.0/0 | PTS,REB,AST |
| Luke Kornet | SAS | 4.8/13 | 0.0/4 | 0.0/1 | 0.0/0 | 0.0/0 | 0.0/1 | MIN,PTS,REB,BLK |
| Ajay Mitchell | OKC | 23.3/23 | 7.0/4 | 2.0/5 | 2.0/6 | 0.0/0 | 0.0/0 | AST |
| Isaiah Hartenstein | OKC | 22.9/17 | 7.0/4 | 8.0/3 | 2.0/3 | 0.0/1 | 0.0/1 | all |
| Mitchell Robinson | BOS | 0.0/18 | 0.0/4 | 0.0/3 | 0.0/1 | 0.0/1 | 0.0/2 | MIN,PTS,REB,AST,STL,BLK |
| Miles McBride | NYK | 13.9/14 | 0.0/3 | 0.0/1 | 0.0/1 | 0.0/0 | 0.0/1 | BLK |
| Harrison Barnes | SAS | 20.1/9 | 2.0/3 | 1.0/0 | 0.0/0 | 0.0/0 | 0.0/1 | MIN,BLK |
| Kenrich Williams | OKC | 5.5/7 | 0.0/3 | 0.0/2 | 0.0/0 | 0.0/0 | 0.0/0 | PTS,REB |
| Daniss Jenkins | DET | 28.8/15 | 14.0/3 | 6.0/2 | 6.0/3 | 1.0/0 | 0.0/0 | MIN |
| Kevin Huerter | DET | 0.0/18 | 0.0/3 | 0.0/3 | 0.0/2 | 0.0/0 | 0.0/0 | MIN,PTS,REB,AST |
| Neemias Queta | BOS | 25.4/22 | 9.0/3 | 8.0/4 | 1.0/2 | 0.0/1 | 1.0/2 | all |
| David Jones Garcia | SAS | 0.0/1 | 0.0/2 | 0.0/0 | 0.0/0 | 0.0/0 | 0.0/0 | MIN,PTS |
| Ja'Kobi Gillespie | SAS | 0.0/1 | 0.0/2 | 0.0/0 | 0.0/0 | 0.0/0 | 0.0/0 | MIN,PTS |
| Luka Garza | BOS | 6.4/8 | 0.0/2 | 0.0/2 | 0.0/0 | 0.0/0 | 0.0/0 | PTS,REB |
| Adem Bona | PHI | 14.5/10 | 0.0/0 | 0.0/3 | 0.0/1 | 0.0/0 | 0.0/1 | AST |
| Jabari Walker | PHI | 0.0/3 | 0.0/0 | 0.0/0 | 0.0/1 | 0.0/0 | 0.0/0 | MIN,AST |
| Carter Bryant | SAS | 2.9/6 | 0.0/0 | 0.0/0 | 0.0/1 | 0.0/0 | 0.0/0 | MIN,AST |
| Maliq Brown | SAS | 0.0/1 | 0.0/0 | 0.0/0 | 0.0/1 | 0.0/0 | 0.0/0 | MIN,AST |
| Tarris Reed Jr. | SAS | 0.0/1 | 0.0/0 | 0.0/0 | 0.0/0 | 0.0/0 | 0.0/0 | MIN |
| Ronald Holland II | DET | 0.0/3 | 0.0/0 | 0.0/1 | 0.0/1 | 0.0/0 | 0.0/1 | MIN,REB,AST,BLK |
| Jordan Walsh | BOS | 8.1/13 | 0.0/0 | 0.0/6 | 0.0/1 | 0.0/1 | 0.0/1 | REB,AST,STL,BLK |
| Hugo González | BOS | 5.3/10 | 0.0/0 | 0.0/3 | 0.0/0 | 0.0/0 | 0.0/0 | REB |

## 2026-10-21

| Metric | Value |
| --- | ---: |
| Games graded | 11 |
| Winner accuracy | 72.7% |
| Spread MAE | 17.09 |
| Total MAE | 14.64 |
| MIN MAE | 9.92 |
| PTS MAE | 7.23 |
| REB MAE | 3.05 |
| AST MAE | 1.76 |
| 10–90 coverage | 62.6% |
| Top picks hit rate | 33.3% (3/9) |
| Top picks avg claimed confidence | 77.1% |

### Games

| Matchup | Pred winner | Actual | Hit | Pred score | Actual score | Pred margin | Act margin | Pred total | Act total |
| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: |
| MIN@MIA | MIN (50%) | MIN | Y | MIN 121 – MIA 121 | MIN 131 – MIA 106 | -1.0 | -25.0 | 242.0 | 237.0 |
| GSW@LAL | LAL (68%) | LAL | Y | GSW 116 – LAL 127 | GSW 105 – LAL 127 | +11.0 | +22.0 | 244.0 | 232.0 |
| ATL@ORL | ORL (59%) | ATL | N | ATL 116 – ORL 120 | ATL 132 – ORL 125 | +6.0 | -7.0 | 236.0 | 257.0 |
| MIL@WAS | MIL (53%) | WAS | N | MIL 123 – WAS 121 | MIL 116 – WAS 128 | -3.0 | +12.0 | 243.0 | 244.0 |
| CHA@BKN | CHA (85%) | CHA | Y | CHA 133 – BKN 109 | CHA 110 – BKN 103 | -24.0 | -7.0 | 242.0 | 213.0 |
| CHI@TOR | TOR (61%) | TOR | Y | CHI 116 – TOR 122 | CHI 92 – TOR 135 | +7.0 | +43.0 | 238.0 | 227.0 |
| UTA@MEM | MEM (66%) | MEM | Y | UTA 114 – MEM 123 | UTA 103 – MEM 123 | +9.0 | +20.0 | 238.0 | 226.0 |
| IND@NOP | NOP (53%) | IND | N | IND 120 – NOP 122 | IND 123 – NOP 120 | +2.0 | -3.0 | 242.0 | 243.0 |
| DAL@HOU | HOU (64%) | HOU | Y | DAL 114 – HOU 121 | DAL 110 – HOU 128 | +8.0 | +18.0 | 235.0 | 238.0 |
| PHX@POR | POR (72%) | POR | Y | PHX 115 – POR 128 | PHX 83 – POR 124 | +13.0 | +41.0 | 243.0 | 207.0 |
| SAC@LAC | LAC (61%) | LAC | Y | SAC 121 – LAC 127 | SAC 96 – LAC 121 | +7.0 | +25.0 | 247.0 | 217.0 |

### Top confident picks

| Player | Matchup | Stat | Range | Actual | Hit |
| --- | --- | --- | --- | ---: | --- |
| Gui Santos | GSW vs LAL | AST | 2-6 | 0 | N |
| Onyeka Okongwu | ATL vs ORL | AST | 2-6 | 7 | N |
| Saddiq Bey | NOP vs IND | AST | 2-6 | 0 | N |
| Toumani Camara | POR vs PHX | AST | 2-6 | 3 | Y |
| Andrew Wiggins | MIA vs MIN | AST | 2-6 | 1 | N |
| Jahmai Mashack | MEM vs UTA | AST | 2-6 | — | — |
| Jaden McDaniels | MIN vs MIA | AST | 2-6 | 1 | N |
| Davion Mitchell | MIA vs MIN | REB | 2-6 | 0 | N |
| Nique Clifford | SAC vs LAC | AST | 2-6 | 3 | Y |
| Nickeil Alexander-Walker | ATL vs ORL | AST | 2-6 | 3 | Y |

### Player grades (MIN / PTS / REB / AST / STL / BLK)

| Player | Team | MIN pred/act | PTS | REB | AST | STL | BLK | in 10–90 (any miss listed) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Anthony Edwards | MIN | 36.5/33 | 35.0/45 | 8.0/10 | 6.0/3 | 1.0/2 | 0.0/1 | all |
| Ty Jerome | MEM | 17.1/32 | 2.0/45 | 0.0/7 | 0.0/6 | 0.0/0 | 0.0/1 | MIN,PTS,REB,AST,BLK |
| Giannis Antetokounmpo | MIA | 18.1/30 | 12.0/35 | 5.0/6 | 1.0/1 | 0.0/1 | 0.0/0 | MIN,PTS |
| Paolo Banchero | ORL | 37.1/41 | 28.0/35 | 11.0/7 | 8.0/10 | 1.0/1 | 0.0/0 | MIN |
| Anthony Davis | WAS | 28.3/34 | 25.0/34 | 15.0/12 | 2.0/4 | 1.0/2 | 1.0/1 | all |
| Julius Randle | BKN | 12.2/38 | 0.0/33 | 0.0/8 | 0.0/7 | 0.0/0 | 0.0/1 | MIN,PTS,REB,AST,BLK |
| Cooper Flagg | DAL | 35.9/33 | 22.0/32 | 8.0/5 | 4.0/2 | 1.0/3 | 1.0/1 | all |
| Nickeil Alexander-Walker | ATL | 36.8/30 | 20.0/31 | 5.0/4 | 4.0/3 | 1.0/1 | 0.0/1 | MIN |
| Pascal Siakam | IND | 32.3/35 | 29.0/30 | 9.0/8 | 5.0/1 | 1.0/1 | 0.0/0 | AST |
| Jabari Smith Jr. | HOU | 32.3/36 | 18.0/30 | 10.0/5 | 2.0/1 | 1.0/2 | 1.0/0 | MIN |
| Kevin Durant | HOU | 21.6/37 | 9.0/30 | 2.0/6 | 1.0/3 | 0.0/1 | 0.0/1 | MIN,PTS |
| Darius Garland | LAC | 38.2/32 | 32.0/30 | 5.0/1 | 8.0/4 | 1.0/1 | 0.0/0 | REB |
| Luka Dončić | LAL | 42.0/30 | 43.0/28 | 12.0/8 | 11.0/7 | 2.0/3 | 0.0/0 | MIN |
| Zach LaVine | SAC | 27.5/34 | 18.0/28 | 3.0/4 | 2.0/4 | 0.0/0 | 0.0/0 | MIN |
| Walker Kessler | LAL | 26.1/30 | 14.0/26 | 13.0/9 | 2.0/1 | 1.0/0 | 1.0/2 | MIN |
| Michael Porter Jr. | BKN | 29.4/34 | 25.0/26 | 10.0/7 | 2.0/1 | 1.0/3 | 0.0/0 | STL |
| Damian Lillard | POR | 13.1/24 | 0.0/25 | 0.0/3 | 0.0/6 | 0.0/1 | 0.0/0 | MIN,PTS,AST |
| Tyler Herro | MIL | 12.2/32 | 0.0/24 | 0.0/2 | 0.0/9 | 0.0/1 | 0.0/0 | MIN,PTS,AST,STL |
| Austin Reaves | LAL | 37.5/32 | 30.0/23 | 7.0/4 | 8.0/6 | 1.0/2 | 0.0/1 | MIN |
| Stephen Curry | GSW | 37.5/21 | 39.0/23 | 6.0/2 | 6.0/1 | 1.0/2 | 0.0/0 | MIN,REB,AST |
| Scottie Barnes | TOR | 33.9/26 | 22.0/23 | 10.0/6 | 9.0/5 | 1.0/0 | 1.0/0 | MIN |
| Kawhi Leonard | TOR | 28.5/24 | 27.0/23 | 9.0/6 | 2.0/2 | 2.0/4 | 0.0/1 | all |
| Immanuel Quickley | TOR | 22.6/28 | 8.0/23 | 2.0/4 | 3.0/7 | 0.0/2 | 0.0/0 | PTS |
| Dejounte Murray | NOP | 25.1/34 | 14.0/23 | 5.0/3 | 4.0/7 | 1.0/2 | 0.0/3 | MIN,BLK |
| Tyrese Haliburton | IND | 25.7/34 | 19.0/23 | 4.0/2 | 8.0/12 | 1.0/1 | 0.0/0 | MIN |
| Alperen Sengun | HOU | 32.5/30 | 26.0/23 | 13.0/10 | 7.0/5 | 1.0/0 | 1.0/0 | all |
| Devin Booker | PHX | 36.9/29 | 33.0/23 | 6.0/4 | 8.0/2 | 1.0/1 | 0.0/1 | MIN,AST |
| Wendell Carter Jr. | ORL | 37.2/31 | 16.0/22 | 14.0/7 | 3.0/0 | 1.0/1 | 1.0/0 | MIN,REB,AST |
| Franz Wagner | ORL | 33.4/29 | 26.0/22 | 9.0/6 | 5.0/5 | 1.0/1 | 0.0/0 | all |
| Jaime Jaquez Jr. | MIL | 27.1/31 | 17.0/22 | 7.0/7 | 2.0/2 | 1.0/0 | 0.0/0 | all |
| Keyonte George | UTA | 30.0/29 | 17.0/22 | 4.0/3 | 5.0/5 | 1.0/1 | 0.0/0 | all |
| Zion Williamson | NOP | 29.3/32 | 29.0/22 | 9.0/3 | 5.0/3 | 1.0/3 | 0.0/0 | REB |
| LaMelo Ball | MIN | 15.2/29 | 0.0/21 | 0.0/2 | 0.0/6 | 0.0/2 | 0.0/0 | MIN,PTS,AST,STL |
| Grayson Allen | CHA | 23.0/29 | 12.0/21 | 3.0/3 | 2.0/4 | 1.0/0 | 0.0/0 | all |
| Jalen Johnson | ATL | 37.6/28 | 24.0/20 | 13.0/14 | 7.0/6 | 1.0/0 | 0.0/0 | MIN |
| Dyson Daniels | ATL | 31.1/35 | 11.0/20 | 7.0/4 | 5.0/3 | 2.0/5 | 0.0/0 | STL |
| Trae Young | WAS | 23.1/38 | 15.0/20 | 2.0/0 | 4.0/13 | 0.0/2 | 0.0/0 | MIN,AST |
| Naz Reid | CHA | 28.7/33 | 23.0/20 | 10.0/11 | 2.0/7 | 1.0/0 | 1.0/0 | AST |
| RJ Barrett | TOR | 33.9/26 | 24.0/20 | 8.0/4 | 5.0/3 | 1.0/0 | 0.0/0 | MIN |
| Obi Toppin | IND | 12.1/25 | 0.0/20 | 0.0/3 | 0.0/1 | 0.0/2 | 0.0/0 | MIN,PTS,REB,STL |
| CJ McCollum | ATL | 36.8/25 | 28.0/19 | 6.0/2 | 4.0/3 | 1.0/0 | 0.0/0 | MIN,REB |
| Dennis Schröder | CHA | 8.5/35 | 0.0/19 | 0.0/4 | 0.0/6 | 0.0/0 | 0.0/0 | MIN,PTS,REB,AST |
| Desmond Bane | ORL | 37.1/33 | 23.0/18 | 7.0/5 | 6.0/2 | 1.0/3 | 0.0/0 | AST |
| Kyshawn George | WAS | 14.8/29 | 0.0/18 | 0.0/5 | 0.0/3 | 0.0/1 | 0.0/1 | MIN,PTS,REB,AST,STL,BLK |
| Brandon Miller | CHA | 42.0/36 | 40.0/18 | 9.0/3 | 7.0/1 | 1.0/0 | 1.0/1 | MIN,PTS,REB,AST |
| Lauri Markkanen | UTA | 33.6/36 | 21.0/18 | 9.0/9 | 2.0/3 | 1.0/0 | 0.0/1 | all |
| Andrew Nembhard | IND | 25.5/34 | 16.0/18 | 3.0/2 | 8.0/9 | 1.0/1 | 0.0/0 | MIN |
| Deni Avdija | POR | 37.0/23 | 33.0/18 | 13.0/10 | 8.0/4 | 1.0/2 | 0.0/0 | MIN,PTS,AST |
| Toumani Camara | POR | 37.0/23 | 17.0/18 | 9.0/2 | 4.0/3 | 1.0/0 | 0.0/0 | MIN,REB |
| Jaden McDaniels | MIN | 34.9/29 | 21.0/17 | 8.0/8 | 4.0/1 | 1.0/3 | 1.0/0 | all |
| Moussa Diabaté | CHA | 37.2/34 | 18.0/17 | 17.0/8 | 3.0/3 | 1.0/5 | 1.0/0 | REB,STL |
| Matas Buzelis | CHI | 33.0/25 | 21.0/17 | 8.0/6 | 2.0/0 | 1.0/0 | 1.0/2 | MIN |
| Marcus Sasser | DAL | 7.7/24 | 0.0/17 | 0.0/1 | 0.0/1 | 0.0/1 | 0.0/0 | MIN,PTS,REB,AST,STL |
| Brook Lopez | LAC | 38.5/27 | 22.0/17 | 11.0/11 | 3.0/1 | 1.0/1 | 2.0/1 | MIN |
| Ayo Dosunmu | MIN | 34.4/29 | 21.0/16 | 6.0/5 | 5.0/3 | 1.0/0 | 0.0/0 | all |
| Aaron Wiggins | ATL | 1.6/32 | 0.0/16 | 0.0/3 | 0.0/0 | 0.0/2 | 0.0/0 | MIN,PTS,REB,STL |
| Caleb Wilson | CHI | 0.0/32 | 0.0/16 | 0.0/4 | 0.0/0 | 0.0/3 | 0.0/1 | MIN,PTS,REB,STL,BLK |
| Ivica Zubac | IND | 26.4/34 | 19.0/16 | 14.0/15 | 2.0/0 | 0.0/0 | 1.0/2 | MIN |
| Amen Thompson | HOU | 32.4/33 | 18.0/16 | 10.0/10 | 6.0/4 | 1.0/1 | 0.0/0 | all |
| Naji Marshall | DAL | 36.4/29 | 17.0/16 | 7.0/2 | 5.0/6 | 1.0/1 | 0.0/0 | MIN,REB |
| Bam Adebayo | MIA | 34.7/31 | 29.0/15 | 16.0/7 | 5.0/4 | 1.0/3 | 1.0/0 | PTS,REB |
| Kasparas Jakučionis | MIL | 0.0/26 | 0.0/15 | 0.0/3 | 0.0/3 | 0.0/0 | 0.0/1 | MIN,PTS,REB,AST,BLK |
| Jalen Smith | CHI | 14.7/19 | 0.0/15 | 0.0/8 | 0.0/1 | 0.0/0 | 0.0/1 | PTS,REB,BLK |
| Norman Powell | CHI | 8.7/22 | 0.0/15 | 0.0/5 | 0.0/1 | 0.0/1 | 0.0/0 | MIN,PTS,REB,AST,STL |
| Jerami Grant | MEM | 9.4/24 | 0.0/15 | 0.0/2 | 0.0/3 | 0.0/0 | 0.0/1 | MIN,PTS,AST,BLK |
| Jaren Jackson Jr. | UTA | 29.9/28 | 22.0/15 | 8.0/5 | 1.0/2 | 1.0/1 | 1.0/2 | all |
| Kyrie Irving | DAL | 36.4/24 | 26.0/15 | 6.0/4 | 4.0/2 | 1.0/1 | 0.0/0 | MIN |
| Scoot Henderson | POR | 30.8/19 | 22.0/15 | 5.0/2 | 6.0/1 | 1.0/1 | 0.0/0 | MIN,AST |
| Keaton Wagler | LAC | 0.0/29 | 0.0/15 | 0.0/5 | 0.0/5 | 0.0/2 | 0.0/0 | MIN,PTS,REB,AST,STL |
| Precious Achiuwa | SAC | 33.5/29 | 14.0/15 | 12.0/5 | 2.0/2 | 1.0/2 | 1.0/0 | all |
| Brandon Williams | GSW | 10.1/18 | 0.0/14 | 0.0/4 | 0.0/3 | 0.0/3 | 0.0/0 | MIN,PTS,REB,AST,STL |
| Tristan da Silva | ORL | 9.7/28 | 0.0/14 | 0.0/2 | 0.0/3 | 0.0/1 | 0.0/1 | MIN,PTS,REB,AST,STL,BLK |
| Ja Morant | POR | 15.5/23 | 0.0/14 | 0.0/5 | 0.0/8 | 0.0/3 | 0.0/0 | MIN,REB,AST,STL |
| Domantas Sabonis | SAC | 30.0/34 | 21.0/14 | 16.0/18 | 5.0/8 | 1.0/1 | 0.0/0 | all |
| Tre Jones | CHI | 30.0/13 | 17.0/13 | 5.0/3 | 7.0/0 | 1.0/0 | 0.0/0 | MIN,AST |
| Saddiq Bey | NOP | 34.6/24 | 20.0/13 | 8.0/5 | 4.0/0 | 1.0/0 | 0.0/0 | MIN,AST |
| Yves Missi | NOP | 17.4/30 | 0.0/13 | 0.0/14 | 0.0/5 | 0.0/2 | 0.0/3 | MIN,PTS,REB,AST,STL,BLK |
| Isaiah Jackson | LAC | 0.0/15 | 0.0/13 | 0.0/5 | 0.0/0 | 0.0/1 | 0.0/0 | MIN,PTS,REB,STL |
| Jonathan Kuminga | MIN | 10.0/30 | 0.0/12 | 0.0/1 | 0.0/3 | 0.0/4 | 0.0/1 | MIN,PTS,AST,STL,BLK |
| Gui Santos | GSW | 37.6/25 | 18.0/12 | 9.0/5 | 4.0/0 | 1.0/1 | 0.0/0 | MIN,AST |
| Yaxel Lendeborg | GSW | 0.0/29 | 0.0/12 | 0.0/3 | 0.0/2 | 0.0/1 | 0.0/0 | MIN,PTS,REB,AST,STL |
| Brayden Burries | MIL | 0.0/16 | 0.0/12 | 0.0/5 | 0.0/0 | 0.0/0 | 0.0/0 | MIN,PTS,REB |
| GG Jackson | MEM | 28.8/19 | 22.0/12 | 9.0/8 | 3.0/0 | 1.0/0 | 0.0/2 | MIN,AST |
| Jaylen Wells | MEM | 16.3/28 | 0.0/12 | 0.0/5 | 0.0/0 | 0.0/4 | 0.0/0 | MIN,REB,STL |
| Ace Bailey | UTA | 36.1/24 | 16.0/12 | 7.0/5 | 2.0/3 | 1.0/0 | 1.0/3 | MIN,BLK |
| Gradey Dick | LAC | 8.1/19 | 0.0/12 | 0.0/4 | 0.0/0 | 0.0/0 | 0.0/1 | MIN,PTS,REB,BLK |
| Darius Acuff Jr. | SAC | 0.0/35 | 0.0/12 | 0.0/3 | 0.0/3 | 0.0/3 | 0.0/0 | MIN,PTS,REB,AST,STL |
| Andrew Wiggins | MIA | 36.9/27 | 25.0/11 | 8.0/2 | 4.0/1 | 1.0/0 | 1.0/0 | MIN,PTS,REB |
| Davion Mitchell | MIA | 36.9/33 | 15.0/11 | 4.0/0 | 9.0/11 | 1.0/0 | 0.0/1 | REB |
| Bilal Coulibaly | WAS | 23.1/29 | 8.0/11 | 4.0/2 | 2.0/1 | 1.0/4 | 0.0/2 | MIN,STL,BLK |
| Deandre Ayton | WAS | 0.0/15 | 0.0/11 | 0.0/4 | 0.0/0 | 0.0/0 | 0.0/2 | MIN,PTS,REB,BLK |
| Myles Turner | MIL | 24.1/32 | 17.0/11 | 7.0/5 | 1.0/3 | 0.0/0 | 1.0/1 | MIN |
| Trey Murphy III | NOP | 25.3/32 | 15.0/11 | 5.0/4 | 4.0/1 | 1.0/0 | 0.0/0 | MIN |
| Bennedict Mathurin | NOP | 7.8/18 | 0.0/11 | 0.0/3 | 0.0/2 | 0.0/1 | 0.0/0 | MIN,PTS,REB,AST,STL |
| Donovan Clingan | POR | 25.6/21 | 15.0/11 | 16.0/7 | 2.0/2 | 0.0/0 | 1.0/0 | all |
| Klay Thompson | MIA | 0.0/16 | 0.0/10 | 0.0/1 | 0.0/0 | 0.0/0 | 0.0/0 | MIN,PTS,REB |
| Terrence Shannon Jr | MIN | 15.6/20 | 0.0/10 | 0.0/1 | 0.0/1 | 0.0/0 | 0.0/0 | all |
| Jake LaRavia | LAL | 27.5/18 | 12.0/10 | 6.0/2 | 3.0/2 | 1.0/1 | 0.0/0 | MIN,REB |
| Quentin Grimes | LAL | 21.4/27 | 9.0/10 | 3.0/2 | 1.0/4 | 0.0/1 | 0.0/1 | MIN |
| Gary Payton II | GSW | 19.2/18 | 4.0/10 | 2.0/1 | 1.0/0 | 0.0/0 | 0.0/0 | all |
| Jock Landale | ATL | 17.6/19 | 0.0/10 | 0.0/2 | 0.0/3 | 0.0/0 | 0.0/1 | PTS,AST,BLK |
| Bub Carrington | WAS | 30.7/18 | 15.0/10 | 6.0/1 | 8.0/4 | 1.0/2 | 0.0/0 | MIN,REB |
| Ja'Kobe Walter | TOR | 33.5/23 | 13.0/10 | 6.0/3 | 2.0/4 | 1.0/3 | 0.0/0 | MIN |
| Svi Mykhailiuk | UTA | 0.0/19 | 0.0/10 | 0.0/1 | 0.0/2 | 0.0/3 | 0.0/0 | MIN,PTS,REB,AST,STL |
| Derik Queen | NOP | 21.8/18 | 6.0/10 | 4.0/10 | 2.0/1 | 0.0/2 | 0.0/0 | all |
| Marcus Smart | HOU | 26.2/26 | 8.0/10 | 2.0/2 | 1.0/2 | 1.0/1 | 0.0/0 | all |
| P.J. Washington | DAL | 35.3/31 | 17.0/10 | 10.0/4 | 3.0/2 | 1.0/0 | 1.0/1 | REB |
| Dillon Brooks | PHX | 36.9/27 | 22.0/10 | 6.0/4 | 2.0/0 | 1.0/0 | 0.0/0 | MIN,PTS |
| Jalen Green | PHX | 36.7/25 | 26.0/10 | 8.0/2 | 3.0/3 | 1.0/0 | 0.0/1 | MIN,PTS,REB |
| Rui Hachimura | LAC | 41.5/32 | 24.0/10 | 9.0/8 | 1.0/2 | 1.0/1 | 0.0/1 | MIN,PTS |
| Ziaire Williams | LAL | 20.4/24 | 7.0/9 | 3.0/3 | 1.0/4 | 1.0/1 | 0.0/0 | MIN,AST |
| LJ Cryer | GSW | 1.4/9 | 0.0/9 | 0.0/1 | 0.0/3 | 0.0/0 | 0.0/0 | MIN,PTS,REB,AST |
| Ryan Rollins | MIL | 0.0/24 | 0.0/9 | 0.0/6 | 0.0/3 | 0.0/0 | 0.0/0 | MIN,PTS,REB,AST |
| Noah Clowney | BKN | 22.9/22 | 10.0/9 | 5.0/3 | 1.0/1 | 0.0/1 | 0.0/0 | all |
| Trayce Jackson-Davis | TOR | 0.0/10 | 0.0/9 | 0.0/1 | 0.0/0 | 0.0/0 | 0.0/0 | MIN,PTS,REB |
| Scotty Pippen Jr. | MEM | 27.2/20 | 22.0/9 | 5.0/2 | 8.0/5 | 2.0/3 | 0.0/0 | MIN |
| Darryn Peterson | UTA | 0.0/31 | 0.0/9 | 0.0/4 | 0.0/3 | 0.0/0 | 0.0/0 | MIN,PTS,REB,AST |
| Will Richard | GSW | 9.5/20 | 0.0/8 | 0.0/5 | 0.0/1 | 0.0/1 | 0.0/0 | MIN,PTS,REB,AST,STL |
| Graham Ike | GSW | 0.0/12 | 0.0/8 | 0.0/2 | 0.0/1 | 0.0/1 | 0.0/1 | MIN,PTS,REB,AST,STL,BLK |
| Onyeka Okongwu | ATL | 36.7/29 | 19.0/8 | 13.0/5 | 4.0/7 | 1.0/0 | 1.0/0 | MIN,PTS,REB,AST |
| Luguentz Dort | ATL | 7.1/28 | 0.0/8 | 0.0/4 | 0.0/0 | 0.0/1 | 0.0/0 | MIN,PTS,REB,STL |
| Justin Champagnie | WAS | 22.6/21 | 7.0/8 | 6.0/8 | 1.0/1 | 0.0/0 | 0.0/0 | all |
| Tre Johnson | WAS | 14.8/19 | 0.0/8 | 0.0/1 | 0.0/0 | 0.0/0 | 0.0/1 | BLK |
| Day'Ron Sharpe | BKN | 11.9/30 | 0.0/8 | 0.0/8 | 0.0/3 | 0.0/0 | 0.0/3 | MIN,PTS,REB,AST,BLK |
| Royce O'Neale | CHA | 18.9/17 | 3.0/8 | 2.0/4 | 0.0/0 | 0.0/1 | 0.0/1 | all |
| Jamison Battle | TOR | 22.5/11 | 3.0/8 | 2.0/5 | 0.0/0 | 0.0/1 | 0.0/0 | MIN |
| Jeremiah Fears | NOP | 31.4/21 | 17.0/8 | 5.0/3 | 4.0/1 | 1.0/0 | 0.0/0 | MIN |
| Jrue Holiday | POR | 37.1/21 | 22.0/8 | 8.0/4 | 7.0/1 | 1.0/2 | 0.0/0 | MIN,PTS,REB,AST |
| Oso Ighodaro | PHX | 30.2/15 | 10.0/8 | 9.0/3 | 3.0/3 | 1.0/0 | 1.0/0 | MIN,REB |
| Miles Bridges | PHX | 14.1/29 | 0.0/8 | 0.0/4 | 0.0/0 | 0.0/1 | 0.0/1 | MIN,BLK |
| Derrick Jones Jr. | LAC | 38.6/26 | 22.0/8 | 9.0/6 | 2.0/5 | 2.0/1 | 1.0/0 | MIN,PTS |
| Emanuel Sharp | SAC | 0.0/17 | 0.0/8 | 0.0/1 | 0.0/0 | 0.0/1 | 0.0/0 | MIN,PTS,REB,STL |
| Bobby Portis Jr. | MIA | 11.9/25 | 0.0/7 | 0.0/4 | 0.0/1 | 0.0/1 | 0.0/1 | MIN,STL,BLK |
| Georges Niang | GSW | 9.0/20 | 0.0/7 | 0.0/2 | 0.0/2 | 0.0/2 | 0.0/0 | MIN,PTS,REB,AST,STL |
| Kel'el Ware | MIL | 7.4/14 | 0.0/7 | 0.0/3 | 0.0/1 | 0.0/1 | 0.0/0 | MIN,PTS,REB,AST,STL |
| Keon Ellis | BKN | 0.0/34 | 0.0/7 | 0.0/2 | 0.0/4 | 0.0/2 | 0.0/1 | MIN,PTS,REB,AST,STL,BLK |
| Moritz Wagner | BKN | 0.0/16 | 0.0/7 | 0.0/0 | 0.0/1 | 0.0/0 | 0.0/0 | MIN,PTS,AST |
| Cedric Coward | MEM | 16.9/28 | 0.0/7 | 0.0/7 | 0.0/2 | 0.0/0 | 0.0/1 | MIN,REB,BLK |
| Cameron Boozer | MEM | 0.0/33 | 0.0/7 | 0.0/11 | 0.0/5 | 0.0/0 | 0.0/0 | MIN,PTS,REB,AST |
| Quinten Post | MEM | 0.0/19 | 0.0/7 | 0.0/1 | 0.0/0 | 0.0/0 | 0.0/0 | MIN,PTS,REB |
| Isaiah Collier | UTA | 32.1/16 | 13.0/7 | 4.0/3 | 10.0/3 | 1.0/1 | 0.0/0 | MIN,AST |
| Kris Dunn | LAC | 40.0/27 | 15.0/7 | 8.0/5 | 7.0/7 | 3.0/3 | 0.0/2 | MIN,BLK |
| Kevon Looney | LAL | 12.4/15 | 0.0/6 | 0.0/5 | 0.0/1 | 0.0/0 | 0.0/0 | PTS |
| Jalen Suggs | ORL | 37.2/32 | 21.0/6 | 7.0/3 | 7.0/5 | 2.0/2 | 1.0/0 | PTS,REB |
| Goga Bitadze | ORL | 9.6/12 | 0.0/6 | 0.0/6 | 0.0/1 | 0.0/0 | 0.0/0 | PTS,REB,AST |
| Alex Sarr | WAS | 14.7/24 | 0.0/6 | 0.0/9 | 0.0/2 | 0.0/0 | 0.0/0 | MIN,REB |
| AJ Green | MIL | 34.7/15 | 17.0/6 | 5.0/0 | 3.0/1 | 0.0/0 | 0.0/0 | MIN,REB |
| Mikel Brown Jr. | BKN | 0.0/20 | 0.0/6 | 0.0/3 | 0.0/3 | 0.0/0 | 0.0/0 | MIN,PTS,REB,AST |
| Collin Murray-Boyles | TOR | 17.1/20 | 0.0/6 | 0.0/8 | 0.0/3 | 0.0/1 | 0.0/1 | REB,AST |
| Zach Edey | MEM | 28.5/21 | 24.0/6 | 18.0/9 | 2.0/0 | 1.0/0 | 2.0/2 | MIN,PTS |
| Quenton Jackson | IND | 17.2/16 | 0.0/6 | 0.0/4 | 0.0/1 | 0.0/3 | 0.0/0 | STL |
| Fred VanVleet | HOU | 32.4/30 | 17.0/6 | 4.0/2 | 6.0/11 | 1.0/3 | 0.0/1 | PTS,AST |
| Morez Johnson Jr. | DAL | 0.0/14 | 0.0/6 | 0.0/3 | 0.0/1 | 0.0/0 | 0.0/0 | MIN,PTS,REB,AST |
| Nique Clifford | SAC | 36.1/17 | 15.0/6 | 7.0/1 | 4.0/3 | 1.0/1 | 0.0/0 | MIN,PTS,REB |
| De'Andre Hunter | SAC | 29.6/20 | 18.0/6 | 5.0/3 | 1.0/1 | 0.0/0 | 0.0/0 | MIN |
| Rudy Gobert | MIN | 31.0/33 | 19.0/5 | 19.0/15 | 3.0/1 | 1.0/0 | 1.5/0 | PTS |
| Sandro Mamukelashvili | LAL | 0.0/22 | 0.0/5 | 0.0/4 | 0.0/2 | 0.0/2 | 0.0/0 | MIN,PTS,REB,AST,STL |
| Ousmane Dieng | MIL | 34.7/21 | 17.0/5 | 8.0/4 | 4.0/3 | 1.0/0 | 0.0/0 | MIN,PTS |
| Kyle Kuzma | MIL | 23.7/27 | 14.0/5 | 5.0/6 | 2.0/3 | 0.0/3 | 0.0/0 | STL |
| Allen Graves | TOR | 0.0/19 | 0.0/5 | 0.0/5 | 0.0/0 | 0.0/1 | 0.0/3 | MIN,PTS,REB,STL,BLK |
| Jaxson Hayes | UTA | 4.3/26 | 0.0/5 | 0.0/5 | 0.0/3 | 0.0/2 | 0.0/6 | MIN,PTS,REB,AST,STL,BLK |
| Herbert Jones | NOP | 24.8/17 | 9.0/5 | 4.0/2 | 3.0/0 | 1.0/1 | 0.0/0 | MIN |
| Bogdan Bogdanović | HOU | 0.0/13 | 0.0/5 | 0.0/1 | 0.0/2 | 0.0/0 | 0.0/0 | MIN,PTS,REB,AST |
| Max Christie | DAL | 34.3/29 | 12.0/5 | 4.0/3 | 2.0/2 | 1.0/0 | 0.0/0 | all |
| Yang Hansen | POR | 0.0/12 | 0.0/5 | 0.0/3 | 0.0/0 | 0.0/0 | 0.0/0 | MIN,PTS,REB |
| Duop Reath | PHX | 0.0/9 | 0.0/5 | 0.0/1 | 0.0/0 | 0.0/0 | 0.0/0 | MIN,PTS,REB |
| Nikola Jović | MIA | 18.6/24 | 5.0/4 | 2.0/4 | 1.0/2 | 0.0/0 | 0.0/1 | MIN |
| Nick Richards | MIA | 4.9/3 | 0.0/4 | 0.0/1 | 0.0/0 | 0.0/0 | 0.0/0 | PTS,REB |
| Myron Gardner | MIA | 0.0/3 | 0.0/4 | 0.0/2 | 0.0/0 | 0.0/0 | 0.0/0 | MIN,PTS,REB |
| Egor Dëmin | BKN | 24.5/27 | 11.0/4 | 4.0/4 | 3.0/2 | 1.0/1 | 0.0/0 | all |
| Ryan Kalkbrenner | CHA | 22.8/14 | 10.0/4 | 7.0/5 | 1.0/3 | 0.0/0 | 1.0/2 | MIN |
| Leonard Miller | CHI | 36.4/26 | 21.0/4 | 14.0/6 | 1.0/1 | 1.0/1 | 0.0/0 | MIN,PTS,REB |
| Isaac Okoro | CHI | 30.5/18 | 12.0/4 | 4.0/0 | 2.0/1 | 1.0/0 | 0.0/0 | MIN,REB |
| Jordan Poole | NOP | 12.0/15 | 0.0/4 | 0.0/2 | 0.0/3 | 0.0/0 | 0.0/0 | REB,AST |
| Kelly Oubre Jr. | IND | 13.9/28 | 0.0/4 | 0.0/2 | 0.0/3 | 0.0/1 | 0.0/1 | MIN,AST,BLK |
| Zaccharie Risacher | DAL | 4.8/27 | 0.0/4 | 0.0/6 | 0.0/2 | 0.0/5 | 0.0/0 | MIN,PTS,REB,AST,STL |
| Micah Potter | POR | 8.9/12 | 0.0/4 | 0.0/3 | 0.0/0 | 0.0/0 | 0.0/0 | PTS,REB |
| Koa Peat | PHX | 0.0/7 | 0.0/4 | 0.0/1 | 0.0/0 | 0.0/0 | 0.0/0 | MIN,PTS,REB |
| Baba Miller | LAC | 0.0/9 | 0.0/4 | 0.0/3 | 0.0/1 | 0.0/0 | 0.0/0 | MIN,PTS,REB,AST |
| Daeqwon Plowden | SAC | 31.0/13 | 16.0/4 | 5.0/2 | 1.0/1 | 0.0/1 | 0.0/0 | MIN |
| Tim Hardaway Jr. | MIA | 9.4/18 | 0.0/3 | 0.0/4 | 0.0/1 | 0.0/1 | 0.0/0 | MIN,REB,AST,STL |
| Bones Hyland | MIN | 7.4/4 | 0.0/3 | 0.0/1 | 0.0/0 | 0.0/0 | 0.0/0 | PTS,REB |
| Jaden Hardy | LAL | 11.6/7 | 0.0/3 | 0.0/2 | 0.0/0 | 0.0/0 | 0.0/0 | all |
| Matisse Thybulle | LAL | 5.5/23 | 0.0/3 | 0.0/3 | 0.0/1 | 0.0/1 | 0.0/1 | MIN,PTS,REB,AST,STL,BLK |
| Nolan Traore | BKN | 18.2/16 | 3.0/3 | 0.0/2 | 1.0/0 | 0.0/0 | 0.0/0 | all |
| Sion James | CHA | 23.0/27 | 7.0/3 | 4.0/3 | 2.0/0 | 0.0/1 | 0.0/0 | all |
| Jakob Poeltl | TOR | 22.1/22 | 6.0/3 | 4.0/6 | 1.0/0 | 0.0/1 | 0.0/1 | all |
| Alijah Martin | TOR | 0.0/5 | 0.0/3 | 0.0/0 | 0.0/0 | 0.0/0 | 0.0/0 | MIN,PTS |
| Jaylin Sellers | CHI | 0.0/14 | 0.0/3 | 0.0/1 | 0.0/2 | 0.0/0 | 0.0/0 | MIN,PTS,REB,AST |
| Cam Spencer | MEM | 0.0/16 | 0.0/3 | 0.0/3 | 0.0/2 | 0.0/1 | 0.0/0 | MIN,PTS,REB,AST,STL |
| Kyle Filipowski | UTA | 27.4/9 | 9.0/3 | 8.0/0 | 2.0/0 | 1.0/1 | 0.0/0 | MIN |
| Jarace Walker | IND | 26.2/19 | 12.0/3 | 6.0/6 | 4.0/2 | 1.0/0 | 0.0/1 | MIN |
| Ben Sheppard | IND | 14.4/12 | 0.0/3 | 0.0/1 | 0.0/0 | 0.0/0 | 0.0/0 | all |
| Reed Sheppard | HOU | 23.4/16 | 5.0/3 | 1.0/2 | 1.0/4 | 0.0/2 | 0.0/0 | MIN |
| Isaiah Crawford | HOU | 0.0/3 | 0.0/3 | 0.0/0 | 0.0/0 | 0.0/0 | 0.0/0 | MIN,PTS |
| Moussa Cissé | DAL | 22.2/2 | 2.0/3 | 4.0/0 | 0.0/0 | 0.0/0 | 0.0/0 | MIN |
| Sidy Cissoko | POR | 8.4/25 | 0.0/3 | 0.0/4 | 0.0/3 | 0.0/0 | 0.0/0 | MIN,PTS,REB,AST |
| Ryan Dunn | PHX | 24.6/14 | 7.0/3 | 6.0/2 | 1.0/0 | 1.0/0 | 0.0/0 | MIN |
| Jordan Goodwin | PHX | 12.0/22 | 0.0/3 | 0.0/4 | 0.0/0 | 0.0/2 | 0.0/0 | MIN,STL |
| Jamaree Bouyea | PHX | 0.0/7 | 0.0/3 | 0.0/2 | 0.0/2 | 0.0/0 | 0.0/0 | MIN,PTS,REB,AST |
| Pat Spencer | PHX | 0.0/7 | 0.0/3 | 0.0/3 | 0.0/1 | 0.0/1 | 0.0/1 | MIN,PTS,REB,AST,STL,BLK |
| Jalen Pickett | LAC | 2.7/2 | 0.0/3 | 0.0/0 | 0.0/0 | 0.0/1 | 0.0/0 | PTS,STL |
| Pelle Larsson | MIA | 29.7/24 | 15.0/2 | 5.0/3 | 4.0/4 | 1.0/1 | 0.0/1 | PTS |
| Chris Mañon | LAL | 11.7/6 | 0.0/2 | 0.0/1 | 0.0/0 | 0.0/0 | 0.0/0 | MIN |
| Bronny James | LAL | 0.0/7 | 0.0/2 | 0.0/0 | 0.0/0 | 0.0/0 | 0.0/0 | MIN,PTS |
| Draymond Green | GSW | 37.7/21 | 17.0/2 | 11.0/4 | 10.0/8 | 2.0/1 | 1.0/1 | MIN,PTS,REB |
| Jase Richardson | ORL | 0.0/14 | 0.0/2 | 0.0/2 | 0.0/3 | 0.0/1 | 0.0/2 | MIN,PTS,REB,AST,STL,BLK |
| Khris Middleton | WAS | 23.1/12 | 11.0/2 | 4.0/2 | 2.0/0 | 0.0/0 | 0.0/0 | MIN |
| Jamal Shead | TOR | 31.0/16 | 9.0/2 | 3.0/2 | 7.0/5 | 1.0/1 | 0.0/0 | MIN |
| Josh Giddey | CHI | 29.3/24 | 21.0/2 | 10.0/7 | 8.0/6 | 1.0/0 | 0.0/0 | PTS |
| Tobe Awaka | CHI | 0.0/14 | 0.0/2 | 0.0/7 | 0.0/2 | 0.0/1 | 0.0/1 | MIN,PTS,REB,AST,STL,BLK |
| Brice Sensabaugh | UTA | 28.2/14 | 11.0/2 | 4.0/2 | 2.0/1 | 0.0/0 | 0.0/0 | MIN |
| Tari Eason | HOU | 27.7/3 | 10.0/2 | 6.0/1 | 1.0/0 | 1.0/1 | 0.0/0 | MIN |
| Daniel Gafford | DAL | 27.5/22 | 11.0/2 | 7.0/3 | 1.0/1 | 0.0/1 | 1.0/2 | all |
| Robert Williams III | POR | 16.2/15 | 0.0/2 | 1.0/10 | 0.0/1 | 0.0/0 | 0.0/1 | all |
| Khaman Maluach | PHX | 6.5/17 | 0.0/2 | 0.0/6 | 0.0/1 | 0.0/0 | 0.0/1 | MIN,PTS,REB,AST,BLK |
| Kobe Sanders | LAC | 24.7/19 | 6.0/2 | 2.0/0 | 1.0/3 | 0.0/3 | 0.0/0 | STL |
| Keegan Murray | SAC | 27.7/28 | 11.0/2 | 6.0/4 | 1.0/0 | 0.0/1 | 0.0/0 | all |
| Trey Lyles | MIN | 10.3/12 | 0.0/1 | 0.0/1 | 0.0/0 | 0.0/0 | 0.0/0 | all |
| Jaylen Clark | MIN | 7.1/3 | 0.0/1 | 0.0/1 | 0.0/1 | 0.0/0 | 0.0/0 | PTS,REB,AST |
| Noa Essengue | CHI | 1.7/10 | 0.0/1 | 0.0/3 | 0.0/0 | 0.0/0 | 0.0/0 | MIN,PTS,REB |
| Vít Krejčí | POR | 5.5/15 | 0.0/1 | 0.0/2 | 0.0/3 | 0.0/2 | 0.0/0 | MIN,PTS,REB,AST,STL |
| Rasheer Fleming | PHX | 4.6/12 | 0.0/1 | 0.0/2 | 0.0/0 | 0.0/1 | 0.0/1 | MIN,PTS,REB,STL,BLK |
| Alex Karaban | SAC | 0.0/5 | 0.0/1 | 0.0/1 | 0.0/0 | 0.0/0 | 0.0/0 | MIN,PTS,REB |
| Simone Fontecchio | MIA | 19.6/3 | 5.0/0 | 2.0/0 | 0.0/0 | 0.0/0 | 0.0/1 | MIN |
| Ryan Conwell | MIA | 0.0/3 | 0.0/0 | 0.0/0 | 0.0/2 | 0.0/0 | 0.0/0 | MIN,AST |
| Cody Williams | MIN | 36.6/3 | 13.0/0 | 6.0/0 | 2.0/0 | 1.0/0 | 0.0/0 | MIN,PTS,REB |
| Isaiah Evans | MIN | 0.0/2 | 0.0/0 | 0.0/1 | 0.0/0 | 0.0/0 | 0.0/0 | MIN,REB |
| Joan Beringer | MIN | 0.0/14 | 0.0/0 | 0.0/6 | 0.0/1 | 0.0/0 | 0.0/0 | MIN,REB,AST |
| Al Horford | GSW | 29.3/17 | 13.0/0 | 9.0/4 | 3.0/2 | 1.0/1 | 1.0/0 | MIN,PTS |
| De'Anthony Melton | GSW | 26.1/21 | 15.0/0 | 5.0/2 | 3.0/2 | 2.0/1 | 0.0/0 | PTS |
| Malevy Leons | GSW | 16.2/9 | 0.0/0 | 0.0/1 | 0.0/0 | 0.0/1 | 0.0/0 | MIN |
| Jamal Cain | ORL | 16.5/14 | 0.0/0 | 0.0/0 | 0.0/0 | 0.0/0 | 0.0/0 | all |
| Nikola Vučević | ORL | 6.9/5 | 0.0/0 | 0.0/1 | 0.0/1 | 0.0/0 | 0.0/0 | REB,AST |
| Kingston Flemings | ATL | 0.0/15 | 0.0/0 | 0.0/4 | 0.0/3 | 0.0/0 | 0.0/1 | MIN,REB,AST,BLK |
| Jericho Sims | MIL | 24.3/2 | 6.0/0 | 8.0/0 | 1.0/0 | 0.0/0 | 0.0/0 | MIN |
| Chaney Johnson | BKN | 14.7/5 | 0.0/0 | 0.0/1 | 0.0/0 | 0.0/0 | 0.0/0 | MIN |
| Liam McNeeley | CHA | 3.0/3 | 0.0/0 | 0.0/1 | 0.0/0 | 0.0/0 | 0.0/0 | REB |
| Christian Anderson | CHA | 0.0/13 | 0.0/0 | 0.0/2 | 0.0/2 | 0.0/2 | 0.0/0 | MIN,REB,AST,STL |
| Kyle Anderson | TOR | 1.7/5 | 0.0/0 | 0.0/1 | 0.0/2 | 0.0/1 | 0.0/0 | MIN,REB,AST,STL |
| Jaden Bradley | TOR | 0.0/5 | 0.0/0 | 0.0/0 | 0.0/0 | 0.0/0 | 0.0/0 | MIN |
| Zach Collins | CHI | 16.4/9 | 0.0/0 | 0.0/5 | 0.0/0 | 0.0/0 | 0.0/0 | MIN |
| Buddy Hield | CHI | 2.7/14 | 0.0/0 | 0.0/2 | 0.0/2 | 0.0/0 | 0.0/0 | MIN,REB,AST |
| Josh Okogie | UTA | 3.8/8 | 0.0/0 | 0.0/1 | 0.0/0 | 0.0/0 | 0.0/0 | REB |
| Larry Nance Jr. | IND | 0.0/5 | 0.0/0 | 0.0/0 | 0.0/0 | 0.0/0 | 0.0/0 | MIN |
| Jae'Sean Tate | HOU | 3.5/2 | 0.0/0 | 0.0/0 | 0.0/0 | 0.0/0 | 0.0/0 | all |
| Bruce Thornton | HOU | 0.0/2 | 0.0/0 | 0.0/0 | 0.0/0 | 0.0/0 | 0.0/0 | MIN |
| Clint Capela | HOU | 0.0/8 | 0.0/0 | 0.0/3 | 0.0/0 | 0.0/0 | 0.0/0 | MIN,REB |
| Sergio de Larrea | DAL | 0.0/7 | 0.0/0 | 0.0/2 | 0.0/1 | 0.0/0 | 0.0/0 | MIN,REB,AST |
| Jayson Kent | POR | 0.0/7 | 0.0/0 | 0.0/1 | 0.0/0 | 0.0/1 | 0.0/0 | MIN,REB,STL |
| Collin Gillespie | PHX | 22.7/21 | 7.0/0 | 3.0/1 | 3.0/2 | 1.0/4 | 0.0/0 | STL |
| Cam Christie | LAC | 3.5/2 | 0.0/0 | 0.0/0 | 0.0/0 | 0.0/0 | 0.0/0 | all |
| Nick Martinelli | LAC | 0.0/2 | 0.0/0 | 0.0/1 | 0.0/1 | 0.0/0 | 0.0/0 | MIN,REB,AST |
| Jonathan Mogbo | SAC | 0.0/8 | 0.0/0 | 0.0/0 | 0.0/0 | 0.0/0 | 0.0/0 | MIN |
