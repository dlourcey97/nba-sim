# NBA Sim Season Scorecard — 2026-27

Graded from `prediction_history` after finals. No sportsbook lines or odds.

## Season to date

| Metric | Value |
| --- | ---: |
| Games graded | 36 |
| Winner accuracy | 61.1% |
| Spread MAE (margin) | 12.51 |
| Total MAE | 17.60 |
| Player MIN MAE | 7.31 |
| Player PTS MAE | 5.39 |
| 10–90 coverage (player stats) | 78.9% |
| Top confident picks hit rate | 60.9% (56/92) |
| Top picks avg claimed confidence | 55.2% |

## Notes

- 2026-10-20: no Top confident picks were produced that night (feature landed with the 2026-10-21 slate).

## 2026-10-20

| Metric | Value |
| --- | ---: |
| Games graded | 3 |
| Winner accuracy | 33.3% |
| Spread MAE | 10.00 |
| Total MAE | 21.67 |
| MIN MAE | 5.30 |
| PTS MAE | 5.49 |
| REB MAE | 2.21 |
| AST MAE | 1.58 |
| 10–90 coverage | 76.0% |
| Top confident picks | n/a (none produced) |

### Games

| Matchup | Pred winner | Actual | Hit | Pred score | Actual score | Pred margin | Act margin | Pred total | Act total |
| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: |
| BOS@DET | BOS (52%) | DET | N | BOS 108 – DET 108 | BOS 113 – DET 121 | -2.0 | +8.0 | 217.0 | 234.0 |
| PHI@NYK | NYK (69%) | PHI | N | PHI 114 – NYK 125 | PHI 106 – NYK 100 | +11.0 | -6.0 | 238.0 | 206.0 |
| OKC@SAS | OKC (63%) | OKC | Y | OKC 121 – SAS 114 | OKC 116 – SAS 104 | -9.0 | -12.0 | 236.0 | 220.0 |

### Player grades (MIN / PTS / REB / AST / STL / BLK)

| Player | Team | MIN pred/act | PTS | REB | AST | STL | BLK | in 10–90 (any miss listed) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Paul George | BOS | 29.2/31 | 14.0/38 | 4.0/5 | 2.0/3 | 1.0/5 | 0.0/0 | PTS,STL |
| Shai Gilgeous-Alexander | OKC | 35.0/36 | 31.0/32 | 6.0/6 | 7.0/4 | 1.0/3 | 0.0/3 | BLK |
| Tyrese Maxey | PHI | 33.4/40 | 22.0/28 | 5.0/4 | 7.0/5 | 2.0/3 | 0.0/3 | BLK |
| Stephon Castle | SAS | 30.8/28 | 19.0/24 | 6.0/7 | 7.0/1 | 1.0/0 | 0.0/0 | AST |
| Cade Cunningham | DET | 36.9/35 | 19.0/22 | 4.0/4 | 8.0/8 | 1.0/1 | 0.0/1 | all |
| Jalen Duren | DET | 24.9/28 | 13.0/22 | 11.0/9 | 2.0/1 | 0.0/1 | 0.0/1 | all |
| Jalen Brunson | NYK | 36.9/34 | 31.0/21 | 5.0/5 | 8.0/3 | 1.0/0 | 0.0/0 | AST |
| Duncan Robinson | DET | 23.2/28 | 9.0/21 | 1.0/2 | 2.0/2 | 0.0/1 | 0.0/0 | all |
| Jared McCain | OKC | 25.3/22 | 12.0/20 | 3.0/2 | 2.0/2 | 0.0/1 | 0.0/0 | all |
| Karl-Anthony Towns | NYK | 30.5/24 | 29.0/19 | 18.0/12 | 4.0/1 | 1.0/1 | 0.0/2 | all |
| Jaylen Brown | PHI | 29.2/35 | 20.0/19 | 7.0/8 | 5.0/6 | 1.0/1 | 0.0/1 | all |
| Javonte Green | DET | 5.7/18 | 0.0/19 | 0.0/4 | 0.0/0 | 0.0/0 | 0.0/0 | MIN,PTS |
| Dylan Harper | SAS | 22.3/32 | 4.0/18 | 2.0/7 | 1.0/5 | 0.0/0 | 0.0/0 | MIN,PTS |
| Derrick White | BOS | 32.2/36 | 14.0/17 | 3.0/1 | 4.0/8 | 1.0/1 | 1.0/0 | all |
| Payton Pritchard | BOS | 30.1/28 | 11.0/17 | 2.0/4 | 4.0/1 | 0.0/0 | 0.0/0 | all |
| Josh Hart | NYK | 35.3/30 | 17.0/14 | 14.0/7 | 7.0/3 | 1.0/1 | 0.0/1 | REB |
| LeBron James | PHI | 31.2/34 | 22.0/14 | 9.0/9 | 9.0/7 | 1.0/1 | 0.0/1 | all |
| De'Aaron Fox | SAS | 35.1/32 | 22.0/14 | 6.0/7 | 7.0/7 | 1.0/1 | 0.0/0 | all |
| Chet Holmgren | OKC | 29.0/31 | 21.0/14 | 13.0/7 | 2.0/2 | 1.0/0 | 2.0/4 | all |
| Joel Embiid | PHI | 29.4/33 | 22.0/13 | 9.0/11 | 4.0/6 | 0.0/2 | 1.0/3 | BLK |
| Anfernee Simons | PHI | 7.8/25 | 0.0/13 | 0.0/2 | 0.0/0 | 0.0/0 | 0.0/0 | MIN,PTS,REB |
| Jayson Tatum | BOS | 30.2/38 | 16.0/13 | 6.0/4 | 3.0/11 | 1.0/0 | 0.0/0 | MIN,AST |
| Andre Drummond | NYK | 0.0/24 | 0.0/12 | 0.0/14 | 0.0/4 | 0.0/1 | 0.0/2 | MIN,PTS,REB,AST,STL,BLK |
| Victor Wembanyama | SAS | 36.1/34 | 31.0/12 | 17.0/13 | 4.0/3 | 1.0/1 | 3.0/6 | PTS |
| Jalen Williams | OKC | 24.1/30 | 15.0/12 | 5.0/7 | 4.0/2 | 1.0/1 | 0.0/1 | all |
| Ausar Thompson | DET | 26.2/33 | 9.0/11 | 5.0/11 | 3.0/5 | 2.0/1 | 0.0/0 | MIN |
| Sam Hauser | BOS | 20.7/18 | 6.0/11 | 2.0/4 | 1.0/1 | 0.0/0 | 0.0/0 | all |
| OG Anunoby | NYK | 36.6/32 | 21.0/10 | 7.0/5 | 2.0/0 | 2.0/1 | 1.0/1 | PTS,AST |
| Kentavious Caldwell-Pope | PHI | 9.4/26 | 0.0/10 | 0.0/4 | 0.0/1 | 0.0/0 | 0.0/1 | MIN,PTS,REB,AST,BLK |
| Keldon Johnson | SAS | 14.8/20 | 0.0/10 | 0.0/4 | 0.0/1 | 0.0/2 | 0.0/0 | MIN,PTS,REB,STL |
| VJ Edgecombe | PHI | 32.9/35 | 13.0/9 | 7.0/4 | 4.5/1 | 1.0/1 | 0.0/0 | AST |
| Alex Caruso | OKC | 28.8/25 | 11.0/9 | 5.0/6 | 4.0/1 | 2.0/1 | 0.0/0 | all |
| Jose Alvarado | NYK | 14.1/16 | 0.0/8 | 0.0/3 | 0.0/3 | 0.0/2 | 0.0/0 | PTS,REB,AST,STL |
| Julian Champagnie | SAS | 29.8/30 | 10.0/8 | 6.0/3 | 2.0/1 | 1.0/2 | 0.0/3 | BLK |
| Isaiah Joe | DET | 9.7/19 | 3.0/8 | 0.0/2 | 0.0/2 | 0.0/1 | 0.0/1 | MIN |
| Baylor Scheierman | BOS | 15.2/18 | 3.0/8 | 2.0/3 | 1.0/0 | 0.0/1 | 0.0/0 | all |
| Devin Vassell | SAS | 35.8/31 | 17.0/7 | 6.0/3 | 3.0/1 | 1.0/0 | 0.0/0 | MIN,PTS |
| Aday Mara | OKC | 0.0/12 | 0.0/7 | 0.0/2 | 0.0/1 | 0.0/0 | 0.0/1 | MIN,PTS,REB,AST,BLK |
| Cason Wallace | OKC | 24.2/19 | 5.0/6 | 3.0/3 | 2.0/2 | 1.0/1 | 0.0/0 | all |
| John Collins | DET | 19.3/25 | 9.0/6 | 5.0/5 | 0.0/1 | 0.0/1 | 0.0/1 | MIN |
| Paul Reed | DET | 8.6/17 | 3.0/6 | 2.0/6 | 0.0/2 | 0.0/1 | 0.0/0 | MIN |
| Landry Shamet | NYK | 17.0/25 | 0.0/5 | 0.0/2 | 0.0/4 | 0.0/0 | 0.0/0 | MIN,AST |
| Jaylin Williams | OKC | 16.2/17 | 0.0/5 | 0.0/4 | 0.0/1 | 0.0/0 | 0.0/0 | all |
| Mikal Bridges | NYK | 36.0/33 | 19.0/4 | 5.0/3 | 4.0/1 | 1.0/0 | 0.0/1 | PTS,AST |
| Jordan Clarkson | NYK | 7.5/8 | 0.0/4 | 0.0/1 | 0.0/1 | 0.0/0 | 0.0/0 | PTS,REB,AST |
| Luke Kornet | SAS | 4.8/13 | 0.0/4 | 0.0/1 | 0.0/0 | 0.0/0 | 0.0/1 | MIN,PTS,REB,BLK |
| Ajay Mitchell | OKC | 23.3/23 | 7.0/4 | 2.0/5 | 2.0/6 | 0.0/0 | 0.0/0 | AST |
| Isaiah Hartenstein | OKC | 22.9/17 | 7.0/4 | 8.0/3 | 2.0/3 | 0.0/1 | 0.0/1 | all |
| Mitchell Robinson | BOS | 12.7/18 | 4.0/4 | 5.0/3 | 0.0/1 | 0.0/1 | 0.0/2 | MIN |
| Miles McBride | NYK | 13.9/14 | 0.0/3 | 0.0/1 | 0.0/1 | 0.0/0 | 0.0/1 | BLK |
| Harrison Barnes | SAS | 20.1/9 | 2.0/3 | 1.0/0 | 0.0/0 | 0.0/0 | 0.0/1 | MIN,BLK |
| Kenrich Williams | OKC | 5.5/7 | 0.0/3 | 0.0/2 | 0.0/0 | 0.0/0 | 0.0/0 | PTS,REB |
| Daniss Jenkins | DET | 28.6/15 | 10.0/3 | 2.0/2 | 4.0/3 | 1.0/0 | 0.0/0 | MIN |
| Kevin Huerter | DET | 0.0/18 | 0.0/3 | 0.0/3 | 0.0/2 | 0.0/0 | 0.0/0 | MIN,PTS,REB,AST |
| Neemias Queta | BOS | 21.8/22 | 8.0/3 | 7.0/4 | 1.0/2 | 0.0/1 | 0.0/2 | all |
| David Jones Garcia | SAS | 0.0/1 | 0.0/2 | 0.0/0 | 0.0/0 | 0.0/0 | 0.0/0 | MIN,PTS |
| Ja'Kobi Gillespie | SAS | 0.0/1 | 0.0/2 | 0.0/0 | 0.0/0 | 0.0/0 | 0.0/0 | MIN,PTS |
| Luka Garza | BOS | 0.0/8 | 0.0/2 | 0.0/2 | 0.0/0 | 0.0/0 | 0.0/0 | MIN,PTS,REB |
| Adem Bona | PHI | 14.5/10 | 0.0/0 | 0.0/3 | 0.0/1 | 0.0/0 | 0.0/1 | AST |
| Jabari Walker | PHI | 0.0/3 | 0.0/0 | 0.0/0 | 0.0/1 | 0.0/0 | 0.0/0 | MIN,AST |
| Carter Bryant | SAS | 2.9/6 | 0.0/0 | 0.0/0 | 0.0/1 | 0.0/0 | 0.0/0 | MIN,AST |
| Maliq Brown | SAS | 0.0/1 | 0.0/0 | 0.0/0 | 0.0/1 | 0.0/0 | 0.0/0 | MIN,AST |
| Tarris Reed Jr. | SAS | 0.0/1 | 0.0/0 | 0.0/0 | 0.0/0 | 0.0/0 | 0.0/0 | MIN |
| Ronald Holland II | DET | 0.0/3 | 0.0/0 | 0.0/1 | 0.0/1 | 0.0/0 | 0.0/1 | MIN,AST,BLK |
| Jordan Walsh | BOS | 11.1/13 | 2.0/0 | 2.0/6 | 0.0/1 | 0.0/1 | 0.0/1 | REB |
| Hugo González | BOS | 0.0/10 | 0.0/0 | 0.0/3 | 0.0/0 | 0.0/0 | 0.0/0 | MIN,REB |

## 2026-10-21

| Metric | Value |
| --- | ---: |
| Games graded | 11 |
| Winner accuracy | 63.6% |
| Spread MAE | 18.18 |
| Total MAE | 14.55 |
| MIN MAE | 7.96 |
| PTS MAE | 5.47 |
| REB MAE | 2.05 |
| AST MAE | 1.41 |
| 10–90 coverage | 77.5% |
| Top picks hit rate | 62.5% (5/8) |
| Top picks avg claimed confidence | 61.0% |

### Games

| Matchup | Pred winner | Actual | Hit | Pred score | Actual score | Pred margin | Act margin | Pred total | Act total |
| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: |
| MIN@MIA | MIA (57%) | MIN | N | MIN 118 – MIA 122 | MIN 131 – MIA 106 | +5.0 | -25.0 | 240.0 | 237.0 |
| GSW@LAL | LAL (60%) | LAL | Y | GSW 114 – LAL 120 | GSW 105 – LAL 127 | +6.0 | +22.0 | 234.0 | 232.0 |
| ATL@ORL | ORL (66%) | ATL | N | ATL 113 – ORL 122 | ATL 132 – ORL 125 | +9.0 | -7.0 | 234.0 | 257.0 |
| MIL@WAS | MIL (51%) | WAS | N | MIL 120 – WAS 120 | MIL 116 – WAS 128 | -1.0 | +12.0 | 240.0 | 244.0 |
| CHA@BKN | CHA (70%) | CHA | Y | CHA 122 – BKN 110 | CHA 110 – BKN 103 | -12.0 | -7.0 | 232.0 | 213.0 |
| CHI@TOR | TOR (62%) | TOR | Y | CHI 122 – TOR 130 | CHI 92 – TOR 135 | +8.0 | +43.0 | 252.0 | 227.0 |
| UTA@MEM | MEM (61%) | MEM | Y | UTA 115 – MEM 120 | UTA 103 – MEM 123 | +7.0 | +20.0 | 235.0 | 226.0 |
| IND@NOP | NOP (55%) | IND | N | IND 115 – NOP 118 | IND 123 – NOP 120 | +4.0 | -3.0 | 233.0 | 243.0 |
| DAL@HOU | HOU (62%) | HOU | Y | DAL 108 – HOU 114 | DAL 110 – HOU 128 | +7.0 | +18.0 | 222.0 | 238.0 |
| PHX@POR | POR (59%) | POR | Y | PHX 113 – POR 118 | PHX 83 – POR 124 | +6.0 | +41.0 | 230.0 | 207.0 |
| SAC@LAC | LAC (58%) | LAC | Y | SAC 119 – LAC 124 | SAC 96 – LAC 121 | +6.0 | +25.0 | 243.0 | 217.0 |

### Top confident picks

| Player | Matchup | Stat | Range | Actual | Hit |
| --- | --- | --- | --- | ---: | --- |
| player:1630217 | ORL vs ATL | AST | 2-6 | 2 | Y |
| player:1627832 | HOU vs DAL | AST | 2-6 | 11 | N |
| player:202695 | TOR vs CHI | STL | 1-3 | 4 | N |
| player:1641708 | HOU vs DAL | AST | 2-6 | 4 | Y |
| player:1629628 | TOR vs CHI | AST | 2-6 | 3 | Y |
| player:1631094 | ORL vs ATL | AST | 3-7 | 10 | N |
| player:1630166 | POR vs PHX | AST | 2-6 | 4 | Y |
| player:1630552 | ATL vs ORL | AST | 2-6 | 6 | Y |

### Player grades (MIN / PTS / REB / AST / STL / BLK)

| Player | Team | MIN pred/act | PTS | REB | AST | STL | BLK | in 10–90 (any miss listed) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Anthony Edwards | MIN | 29.1/33 | 16.0/45 | 3.0/10 | 3.0/3 | 1.0/2 | 0.0/1 | PTS,REB |
| Ty Jerome | MEM | 19.7/32 | 12.0/45 | 2.0/7 | 3.0/6 | 1.0/0 | 0.0/1 | MIN,PTS,REB |
| Giannis Antetokounmpo | MIA | 24.1/30 | 18.0/35 | 8.0/6 | 3.0/1 | 0.0/1 | 0.0/0 | MIN |
| Paolo Banchero | ORL | 34.6/41 | 19.0/35 | 7.0/7 | 5.0/10 | 0.0/1 | 0.0/0 | MIN |
| Anthony Davis | WAS | 21.1/34 | 12.0/34 | 8.0/12 | 1.0/4 | 0.0/2 | 0.0/1 | MIN,PTS,AST |
| Julius Randle | BKN | 25.7/38 | 13.0/33 | 5.0/8 | 2.0/7 | 0.0/0 | 0.0/1 | MIN,PTS,AST |
| Cooper Flagg | DAL | 21.1/33 | 10.0/32 | 3.0/5 | 3.0/2 | 0.0/3 | 0.0/1 | MIN,PTS,STL |
| Nickeil Alexander-Walker | ATL | 29.0/30 | 11.0/31 | 2.0/4 | 3.0/3 | 1.0/1 | 0.0/1 | PTS |
| Pascal Siakam | IND | 19.1/35 | 11.0/30 | 3.0/8 | 2.0/1 | 0.0/1 | 0.0/0 | MIN,PTS |
| Jabari Smith Jr. | HOU | 27.2/36 | 10.0/30 | 5.0/5 | 1.0/1 | 0.0/2 | 0.0/0 | MIN,PTS |
| Kevin Durant | HOU | 25.2/37 | 15.0/30 | 3.0/6 | 3.0/3 | 0.0/1 | 0.0/1 | MIN |
| Darius Garland | LAC | 25.1/32 | 14.0/30 | 1.0/1 | 5.0/4 | 1.0/1 | 0.0/0 | MIN |
| Luka Dončić | LAL | 32.4/30 | 22.0/28 | 6.0/8 | 6.0/7 | 1.0/3 | 0.0/0 | all |
| Zach LaVine | SAC | 20.0/34 | 13.0/28 | 1.0/4 | 2.0/4 | 0.0/0 | 0.0/0 | MIN |
| Walker Kessler | LAL | 30.2/30 | 10.0/26 | 11.0/9 | 1.0/1 | 0.0/0 | 1.0/2 | PTS |
| Michael Porter Jr. | BKN | 25.1/34 | 13.0/26 | 5.0/7 | 2.0/1 | 0.0/3 | 0.0/0 | MIN,STL |
| Damian Lillard | POR | 18.6/24 | 12.0/25 | 2.0/3 | 2.0/6 | 0.0/1 | 0.0/0 | all |
| Tyler Herro | MIL | 18.3/32 | 11.0/24 | 2.0/2 | 2.0/9 | 0.0/1 | 0.0/0 | MIN,AST |
| Austin Reaves | LAL | 37.8/32 | 17.0/23 | 3.0/4 | 5.0/6 | 1.0/2 | 0.0/1 | all |
| Stephen Curry | GSW | 22.0/21 | 13.0/23 | 2.0/2 | 3.0/1 | 0.0/2 | 0.0/0 | all |
| Scottie Barnes | TOR | 30.0/26 | 15.0/23 | 6.0/6 | 7.0/5 | 1.0/0 | 1.0/0 | all |
| Kawhi Leonard | TOR | 26.7/24 | 25.0/23 | 8.0/6 | 2.0/2 | 2.0/4 | 0.0/1 | all |
| Immanuel Quickley | TOR | 16.2/28 | 10.0/23 | 2.0/4 | 4.0/7 | 0.0/2 | 0.0/0 | MIN |
| Dejounte Murray | NOP | 17.6/34 | 8.0/23 | 3.0/3 | 3.0/7 | 1.0/2 | 0.0/3 | MIN,PTS,BLK |
| Tyrese Haliburton | IND | 14.0/34 | 7.0/23 | 1.0/2 | 3.0/12 | 0.0/1 | 0.0/0 | MIN,PTS,AST |
| Alperen Sengun | HOU | 25.2/30 | 14.0/23 | 7.0/10 | 4.0/5 | 1.0/0 | 0.0/0 | all |
| Devin Booker | PHX | 29.6/29 | 16.0/23 | 2.0/4 | 5.0/2 | 0.0/1 | 0.0/1 | all |
| Wendell Carter Jr. | ORL | 30.0/31 | 11.0/22 | 8.0/7 | 2.0/0 | 1.0/1 | 0.0/0 | all |
| Franz Wagner | ORL | 24.4/29 | 14.0/22 | 4.0/6 | 3.0/5 | 1.0/1 | 0.0/0 | all |
| Jaime Jaquez Jr. | MIL | 19.5/31 | 8.0/22 | 3.0/7 | 2.0/2 | 0.0/0 | 0.0/0 | MIN |
| Keyonte George | UTA | 19.7/29 | 10.0/22 | 1.0/3 | 3.0/5 | 0.0/1 | 0.0/0 | MIN |
| Zion Williamson | NOP | 17.6/32 | 11.0/22 | 3.0/3 | 2.0/3 | 0.0/3 | 0.0/0 | MIN,STL |
| LaMelo Ball | MIN | 25.0/29 | 16.0/21 | 4.0/2 | 4.0/6 | 1.0/2 | 0.0/0 | all |
| Grayson Allen | CHA | 17.8/29 | 8.0/21 | 1.0/3 | 1.0/4 | 0.0/0 | 0.0/0 | MIN |
| Jalen Johnson | ATL | 29.7/28 | 13.0/20 | 8.0/14 | 4.0/6 | 1.0/0 | 0.0/0 | all |
| Dyson Daniels | ATL | 21.0/35 | 7.0/20 | 4.0/4 | 3.0/3 | 1.0/5 | 0.0/0 | MIN,PTS,STL |
| Trae Young | WAS | 13.7/38 | 8.0/20 | 1.0/0 | 3.0/13 | 0.0/2 | 0.0/0 | MIN,AST |
| Naz Reid | CHA | 27.6/33 | 12.0/20 | 6.0/11 | 1.0/7 | 1.0/0 | 0.0/0 | AST |
| RJ Barrett | TOR | 30.3/26 | 16.0/20 | 5.0/4 | 4.0/3 | 0.0/0 | 0.0/0 | all |
| Obi Toppin | IND | 12.4/25 | 6.0/20 | 2.0/3 | 1.0/1 | 0.0/2 | 0.0/0 | MIN,PTS,STL |
| CJ McCollum | ATL | 25.7/25 | 14.0/19 | 2.0/2 | 3.0/3 | 0.0/0 | 0.0/0 | all |
| Dennis Schröder | CHA | 13.4/35 | 5.0/19 | 1.0/4 | 2.0/6 | 0.0/0 | 0.0/0 | MIN,PTS,REB,AST |
| Desmond Bane | ORL | 31.4/33 | 15.0/18 | 3.0/5 | 4.0/2 | 1.0/3 | 0.0/0 | STL |
| Kyshawn George | WAS | 13.5/29 | 6.0/18 | 2.0/5 | 2.0/3 | 0.0/1 | 0.0/1 | MIN,PTS |
| Brandon Miller | CHA | 28.8/36 | 17.0/18 | 4.0/3 | 3.0/1 | 1.0/0 | 0.0/1 | MIN |
| Lauri Markkanen | UTA | 21.7/36 | 11.0/18 | 3.0/9 | 1.0/3 | 0.0/0 | 0.0/1 | MIN,REB |
| Andrew Nembhard | IND | 21.0/34 | 8.0/18 | 1.0/2 | 4.0/9 | 0.0/1 | 0.0/0 | MIN |
| Deni Avdija | POR | 27.1/23 | 14.0/18 | 5.0/10 | 4.0/4 | 0.0/2 | 0.0/0 | all |
| Toumani Camara | POR | 26.4/23 | 7.5/18 | 3.0/2 | 2.0/3 | 1.0/0 | 0.0/0 | MIN |
| Jaden McDaniels | MIN | 24.7/29 | 10.0/17 | 3.0/8 | 2.0/1 | 1.0/3 | 0.0/0 | STL |
| Moussa Diabaté | CHA | 23.6/34 | 7.0/17 | 7.0/8 | 1.0/3 | 0.0/5 | 0.0/0 | MIN,STL |
| Matas Buzelis | CHI | 23.7/25 | 10.0/17 | 3.0/6 | 2.0/0 | 0.0/0 | 1.0/2 | all |
| Marcus Sasser | DAL | 12.8/24 | 3.0/17 | 0.0/1 | 1.0/1 | 0.0/1 | 0.0/0 | MIN,PTS |
| Brook Lopez | LAC | 25.3/27 | 10.0/17 | 4.0/11 | 2.0/1 | 0.0/1 | 1.0/1 | REB |
| Ayo Dosunmu | MIN | 22.9/29 | 9.0/16 | 2.0/5 | 3.0/3 | 0.0/0 | 0.0/0 | MIN |
| Aaron Wiggins | ATL | 0.0/32 | 0.0/16 | 0.0/3 | 0.0/0 | 0.0/2 | 0.0/0 | MIN,PTS,REB,STL |
| Caleb Wilson | CHI | 0.0/32 | 0.0/16 | 0.0/4 | 0.0/0 | 0.0/3 | 0.0/1 | MIN,PTS,REB,STL,BLK |
| Ivica Zubac | IND | 16.0/34 | 8.0/16 | 7.0/15 | 1.0/0 | 0.0/0 | 0.0/2 | MIN |
| Amen Thompson | HOU | 27.9/33 | 11.0/16 | 5.0/10 | 4.0/4 | 1.0/1 | 0.0/0 | MIN |
| Naji Marshall | DAL | 22.3/29 | 8.0/16 | 2.0/2 | 3.0/6 | 0.0/1 | 0.0/0 | MIN |
| Bam Adebayo | MIA | 22.8/31 | 12.0/15 | 7.0/7 | 3.0/4 | 1.0/3 | 0.0/0 | MIN,STL |
| Kasparas Jakučionis | MIL | 11.1/26 | 3.0/15 | 1.0/3 | 1.0/3 | 0.0/0 | 0.0/1 | MIN,PTS |
| Norman Powell | CHI | 18.7/22 | 13.0/15 | 1.0/5 | 1.0/1 | 1.0/1 | 0.0/0 | REB |
| Jalen Smith | CHI | 14.8/19 | 8.0/15 | 5.0/8 | 1.0/1 | 0.0/0 | 0.0/1 | all |
| Jerami Grant | MEM | 18.0/24 | 9.0/15 | 1.0/2 | 1.0/3 | 0.0/0 | 0.0/1 | all |
| Jaren Jackson Jr. | UTA | 20.9/28 | 13.0/15 | 4.0/5 | 1.0/2 | 1.0/1 | 0.0/2 | MIN |
| Kyrie Irving | DAL | 23.4/24 | 12.0/15 | 2.0/4 | 2.0/2 | 1.0/1 | 0.0/0 | all |
| Scoot Henderson | POR | 20.3/19 | 9.0/15 | 1.0/2 | 3.0/1 | 0.0/1 | 0.0/0 | all |
| Keaton Wagler | LAC | 0.0/29 | 0.0/15 | 0.0/5 | 0.0/5 | 0.0/2 | 0.0/0 | MIN,PTS,REB,AST,STL |
| Precious Achiuwa | SAC | 25.1/29 | 9.0/15 | 6.0/5 | 1.0/2 | 1.0/2 | 0.0/0 | all |
| Brandon Williams | GSW | 16.0/18 | 6.0/14 | 1.0/4 | 1.0/3 | 0.0/3 | 0.0/0 | STL |
| Tristan da Silva | ORL | 12.6/28 | 5.0/14 | 2.0/2 | 1.0/3 | 0.0/1 | 0.0/1 | MIN |
| Ja Morant | POR | 23.2/23 | 13.0/14 | 2.0/5 | 4.0/8 | 1.0/3 | 0.0/0 | STL |
| Domantas Sabonis | SAC | 22.3/34 | 13.0/14 | 9.0/18 | 3.0/8 | 0.0/1 | 0.0/0 | MIN |
| Tre Jones | CHI | 21.4/13 | 9.0/13 | 2.0/3 | 5.0/0 | 1.0/0 | 0.0/0 | MIN,AST |
| Saddiq Bey | NOP | 20.8/24 | 8.0/13 | 2.0/5 | 1.0/0 | 0.0/0 | 0.0/0 | all |
| Yves Missi | NOP | 17.2/30 | 5.0/13 | 5.0/14 | 1.0/5 | 0.0/2 | 0.0/3 | MIN,REB,AST,STL,BLK |
| Isaiah Jackson | LAC | 14.0/15 | 6.0/13 | 5.0/5 | 1.0/0 | 0.0/1 | 0.0/0 | all |
| Jonathan Kuminga | MIN | 19.0/30 | 10.0/12 | 4.0/1 | 1.0/3 | 0.0/4 | 0.0/1 | MIN,STL |
| Gui Santos | GSW | 19.3/25 | 6.0/12 | 3.0/5 | 2.0/0 | 0.0/1 | 0.0/0 | all |
| Yaxel Lendeborg | GSW | 0.0/29 | 0.0/12 | 0.0/3 | 0.0/2 | 0.0/1 | 0.0/0 | MIN,PTS,REB,AST,STL |
| Brayden Burries | MIL | 0.0/16 | 0.0/12 | 0.0/5 | 0.0/0 | 0.0/0 | 0.0/0 | MIN,PTS,REB |
| GG Jackson | MEM | 18.5/19 | 9.0/12 | 3.0/8 | 1.0/0 | 0.0/0 | 0.0/2 | BLK |
| Jaylen Wells | MEM | 18.2/28 | 7.0/12 | 2.0/5 | 1.0/0 | 0.0/4 | 0.0/0 | MIN,STL |
| Ace Bailey | UTA | 24.6/24 | 8.0/12 | 2.0/5 | 1.0/3 | 0.0/0 | 0.0/3 | BLK |
| Gradey Dick | LAC | 0.0/19 | 0.0/12 | 0.0/4 | 0.0/0 | 0.0/0 | 0.0/1 | MIN,PTS,REB,BLK |
| Darius Acuff Jr. | SAC | 0.0/35 | 0.0/12 | 0.0/3 | 0.0/3 | 0.0/3 | 0.0/0 | MIN,PTS,REB,AST,STL |
| Davion Mitchell | MIA | 31.3/33 | 7.0/11 | 1.0/0 | 5.0/11 | 1.0/0 | 0.0/1 | AST |
| Andrew Wiggins | MIA | 28.0/27 | 12.0/11 | 3.0/2 | 2.0/1 | 1.0/0 | 0.0/0 | all |
| Deandre Ayton | WAS | 14.9/15 | 7.0/11 | 6.0/4 | 0.0/0 | 0.0/0 | 0.0/2 | BLK |
| Bilal Coulibaly | WAS | 13.9/29 | 5.0/11 | 2.0/2 | 1.0/1 | 0.0/4 | 0.0/2 | MIN,STL,BLK |
| Myles Turner | MIL | 14.3/32 | 8.0/11 | 4.0/5 | 1.0/3 | 0.0/0 | 0.0/1 | MIN |
| Trey Murphy III | NOP | 21.4/32 | 9.0/11 | 2.0/4 | 2.0/1 | 0.0/0 | 0.0/0 | MIN |
| Bennedict Mathurin | NOP | 15.7/18 | 8.0/11 | 2.0/3 | 0.5/2 | 0.0/1 | 0.0/0 | all |
| Donovan Clingan | POR | 17.9/21 | 7.0/11 | 9.0/7 | 1.0/2 | 0.0/0 | 1.0/0 | all |
| Klay Thompson | MIA | 15.2/16 | 8.0/10 | 1.0/1 | 1.0/0 | 0.0/0 | 0.0/0 | all |
| Terrence Shannon Jr | MIN | 17.6/20 | 6.0/10 | 1.0/1 | 1.0/1 | 0.0/0 | 0.0/0 | all |
| Quentin Grimes | LAL | 20.5/27 | 8.0/10 | 2.0/2 | 2.0/4 | 0.0/1 | 0.0/1 | MIN |
| Jake LaRavia | LAL | 11.4/18 | 3.0/10 | 1.0/2 | 1.0/2 | 0.0/1 | 0.0/0 | all |
| Gary Payton II | GSW | 14.3/18 | 4.0/10 | 2.0/1 | 1.0/0 | 0.0/0 | 0.0/0 | all |
| Jock Landale | ATL | 19.0/19 | 7.0/10 | 4.0/2 | 1.0/3 | 0.0/0 | 0.0/1 | all |
| Bub Carrington | WAS | 19.8/18 | 6.0/10 | 2.0/1 | 4.0/4 | 0.0/2 | 0.0/0 | STL |
| Ja'Kobe Walter | TOR | 27.0/23 | 9.0/10 | 2.0/3 | 2.0/4 | 1.0/3 | 0.0/0 | all |
| Svi Mykhailiuk | UTA | 14.5/19 | 5.0/10 | 1.0/1 | 1.0/2 | 0.0/3 | 0.0/0 | STL |
| Derik Queen | NOP | 21.8/18 | 8.0/10 | 5.0/10 | 3.0/1 | 1.0/2 | 0.0/0 | all |
| Marcus Smart | HOU | 22.6/26 | 8.0/10 | 1.0/2 | 2.0/2 | 1.0/1 | 0.0/0 | MIN |
| P.J. Washington | DAL | 25.6/31 | 9.0/10 | 4.0/4 | 2.0/2 | 1.0/0 | 0.0/1 | all |
| Jalen Green | PHX | 28.2/25 | 13.0/10 | 3.0/2 | 2.0/3 | 1.0/0 | 0.0/1 | all |
| Dillon Brooks | PHX | 28.0/27 | 11.0/10 | 2.0/4 | 1.0/0 | 1.0/0 | 0.0/0 | all |
| Rui Hachimura | LAC | 32.2/32 | 12.0/10 | 4.0/8 | 1.0/2 | 0.0/1 | 0.0/1 | all |
| Ziaire Williams | LAL | 22.9/24 | 9.0/9 | 3.0/3 | 1.0/4 | 1.0/1 | 0.0/0 | AST |
| LJ Cryer | GSW | 12.9/9 | 5.0/9 | 1.0/1 | 0.0/3 | 0.0/0 | 0.0/0 | AST |
| Ryan Rollins | MIL | 18.8/24 | 8.0/9 | 2.0/6 | 3.0/3 | 1.0/0 | 0.0/0 | REB |
| Noah Clowney | BKN | 18.0/22 | 6.0/9 | 3.0/3 | 1.0/1 | 0.0/1 | 0.0/0 | all |
| Trayce Jackson-Davis | TOR | 0.0/10 | 0.0/9 | 0.0/1 | 0.0/0 | 0.0/0 | 0.0/0 | MIN,PTS |
| Scotty Pippen Jr. | MEM | 18.2/20 | 9.0/9 | 2.0/2 | 3.0/5 | 1.0/3 | 0.0/0 | all |
| Darryn Peterson | UTA | 0.0/31 | 0.0/9 | 0.0/4 | 0.0/3 | 0.0/0 | 0.0/0 | MIN,PTS,REB,AST |
| Graham Ike | GSW | 0.0/12 | 0.0/8 | 0.0/2 | 0.0/1 | 0.0/1 | 0.0/1 | MIN,PTS,AST,STL,BLK |
| Will Richard | GSW | 0.0/20 | 0.0/8 | 0.0/5 | 0.0/1 | 0.0/1 | 0.0/0 | MIN,PTS,REB,AST,STL |
| Onyeka Okongwu | ATL | 28.3/29 | 11.0/8 | 7.0/5 | 2.0/7 | 1.0/0 | 0.0/0 | AST |
| Luguentz Dort | ATL | 16.6/28 | 6.0/8 | 2.0/4 | 0.0/0 | 0.0/1 | 0.0/0 | MIN |
| Justin Champagnie | WAS | 15.8/21 | 6.0/8 | 4.0/8 | 1.0/1 | 0.0/0 | 0.0/0 | all |
| Tre Johnson | WAS | 14.9/19 | 6.0/8 | 1.0/1 | 1.0/0 | 0.0/0 | 0.0/1 | MIN |
| Day'Ron Sharpe | BKN | 15.3/30 | 6.0/8 | 6.0/8 | 1.0/3 | 0.0/0 | 0.0/3 | MIN,BLK |
| Royce O'Neale | CHA | 20.4/17 | 6.0/8 | 3.0/4 | 1.0/0 | 0.0/1 | 0.0/1 | all |
| Jamison Battle | TOR | 16.1/11 | 6.0/8 | 2.0/5 | 1.0/0 | 0.0/1 | 0.0/0 | all |
| Jeremiah Fears | NOP | 24.0/21 | 10.0/8 | 2.0/3 | 3.0/1 | 1.0/0 | 0.0/0 | all |
| Jrue Holiday | POR | 30.2/21 | 10.0/8 | 3.0/4 | 5.0/1 | 1.0/2 | 0.0/0 | MIN |
| Oso Ighodaro | PHX | 24.2/15 | 6.0/8 | 4.0/3 | 2.0/3 | 0.0/0 | 0.0/0 | MIN |
| Miles Bridges | PHX | 23.6/29 | 11.0/8 | 4.0/4 | 2.0/0 | 0.0/1 | 0.0/1 | all |
| Derrick Jones Jr. | LAC | 19.2/26 | 8.0/8 | 3.0/6 | 1.0/5 | 1.0/1 | 0.0/0 | MIN,AST |
| Emanuel Sharp | SAC | 0.0/17 | 0.0/8 | 0.0/1 | 0.0/0 | 0.0/1 | 0.0/0 | MIN,PTS,REB,STL |
| Bobby Portis Jr. | MIA | 20.8/25 | 8.0/7 | 5.0/4 | 1.0/1 | 0.0/1 | 0.0/1 | all |
| Georges Niang | GSW | 14.8/20 | 5.0/7 | 1.0/2 | 0.0/2 | 0.0/2 | 0.0/0 | MIN,STL |
| Kel'el Ware | MIL | 17.5/14 | 8.0/7 | 8.0/3 | 0.0/1 | 0.0/1 | 0.0/0 | all |
| Keon Ellis | BKN | 0.0/34 | 0.0/7 | 0.0/2 | 0.0/4 | 0.0/2 | 0.0/1 | MIN,PTS,REB,AST,STL,BLK |
| Moritz Wagner | BKN | 0.0/16 | 0.0/7 | 0.0/0 | 0.0/1 | 0.0/0 | 0.0/0 | MIN,PTS,AST |
| Cedric Coward | MEM | 18.3/28 | 8.0/7 | 4.0/7 | 2.0/2 | 0.0/0 | 0.0/1 | MIN |
| Quinten Post | MEM | 10.9/19 | 4.0/7 | 2.0/1 | 0.0/0 | 0.0/0 | 0.0/0 | MIN |
| Cameron Boozer | MEM | 0.0/33 | 0.0/7 | 0.0/11 | 0.0/5 | 0.0/0 | 0.0/0 | MIN,PTS,REB,AST |
| Isaiah Collier | UTA | 21.3/16 | 7.0/7 | 1.0/3 | 5.0/3 | 1.0/1 | 0.0/0 | MIN |
| Kris Dunn | LAC | 22.6/27 | 6.0/7 | 3.0/5 | 4.0/7 | 1.0/3 | 0.0/2 | BLK |
| Kevon Looney | LAL | 19.0/15 | 3.0/6 | 6.0/5 | 1.0/1 | 0.0/0 | 0.0/0 | all |
| Jalen Suggs | ORL | 31.1/32 | 13.0/6 | 3.0/3 | 5.0/5 | 1.0/2 | 0.0/0 | all |
| Goga Bitadze | ORL | 11.5/12 | 4.0/6 | 5.0/6 | 1.0/1 | 0.0/0 | 0.0/0 | all |
| Alex Sarr | WAS | 13.6/24 | 7.0/6 | 4.0/9 | 1.0/2 | 0.0/0 | 0.0/0 | MIN |
| AJ Green | MIL | 21.3/15 | 6.0/6 | 1.0/0 | 1.0/1 | 0.0/0 | 0.0/0 | all |
| Mikel Brown Jr. | BKN | 0.0/20 | 0.0/6 | 0.0/3 | 0.0/3 | 0.0/0 | 0.0/0 | MIN,PTS,REB,AST |
| Collin Murray-Boyles | TOR | 21.1/20 | 9.0/6 | 5.0/8 | 2.0/3 | 1.0/1 | 0.0/1 | all |
| Zach Edey | MEM | 21.1/21 | 11.0/6 | 10.0/9 | 1.0/0 | 0.0/0 | 1.0/2 | all |
| Quenton Jackson | IND | 17.5/16 | 7.0/6 | 1.0/4 | 2.0/1 | 0.0/3 | 0.0/0 | STL |
| Fred VanVleet | HOU | 26.6/30 | 9.0/6 | 1.0/2 | 4.0/11 | 1.0/3 | 0.0/1 | AST |
| Morez Johnson Jr. | DAL | 0.0/14 | 0.0/6 | 0.0/3 | 0.0/1 | 0.0/0 | 0.0/0 | MIN,PTS,REB,AST |
| Nique Clifford | SAC | 30.9/17 | 9.0/6 | 3.0/1 | 3.0/3 | 1.0/1 | 0.0/0 | MIN |
| De'Andre Hunter | SAC | 19.6/20 | 10.0/6 | 2.0/3 | 1.0/1 | 0.0/0 | 0.0/0 | all |
| Rudy Gobert | MIN | 21.3/33 | 9.0/5 | 10.0/15 | 2.0/1 | 0.0/0 | 1.0/0 | MIN |
| Sandro Mamukelashvili | LAL | 12.2/22 | 5.0/5 | 3.0/4 | 1.0/2 | 0.0/2 | 0.0/0 | MIN,STL |
| Ousmane Dieng | MIL | 21.0/21 | 7.0/5 | 3.0/4 | 2.0/3 | 0.0/0 | 0.0/0 | all |
| Kyle Kuzma | MIL | 13.4/27 | 7.0/5 | 3.0/6 | 1.0/3 | 0.0/3 | 0.0/0 | MIN,STL |
| Allen Graves | TOR | 0.0/19 | 0.0/5 | 0.0/5 | 0.0/0 | 0.0/1 | 0.0/3 | MIN,PTS,REB,STL,BLK |
| Jaxson Hayes | UTA | 13.9/26 | 5.0/5 | 3.0/5 | 0.0/3 | 0.0/2 | 0.0/6 | MIN,AST,STL,BLK |
| Herbert Jones | NOP | 13.2/17 | 4.0/5 | 1.0/2 | 1.0/0 | 1.0/1 | 0.0/0 | all |
| Bogdan Bogdanović | HOU | 8.5/13 | 3.0/5 | 1.0/1 | 1.0/2 | 0.0/0 | 0.0/0 | all |
| Max Christie | DAL | 20.4/29 | 6.0/5 | 1.0/3 | 1.0/2 | 0.0/0 | 0.0/0 | MIN |
| Yang Hansen | POR | 0.0/12 | 0.0/5 | 0.0/3 | 0.0/0 | 0.0/0 | 0.0/0 | MIN,PTS,REB |
| Duop Reath | PHX | 8.4/9 | 2.0/5 | 1.0/1 | 0.0/0 | 0.0/0 | 0.0/0 | all |
| Nikola Jović | MIA | 19.2/24 | 7.0/4 | 3.0/4 | 2.0/2 | 0.0/0 | 0.0/1 | all |
| Nick Richards | MIA | 16.0/3 | 7.0/4 | 7.0/1 | 0.0/0 | 0.0/0 | 0.0/0 | all |
| Myron Gardner | MIA | 0.0/3 | 0.0/4 | 0.0/2 | 0.0/0 | 0.0/0 | 0.0/0 | MIN,PTS |
| Egor Dëmin | BKN | 20.9/27 | 8.0/4 | 2.0/4 | 2.0/2 | 0.0/1 | 0.0/0 | MIN |
| Ryan Kalkbrenner | CHA | 16.5/14 | 6.0/4 | 4.0/5 | 1.0/3 | 0.0/0 | 0.0/2 | AST |
| Leonard Miller | CHI | 29.5/26 | 12.0/4 | 8.0/6 | 1.0/1 | 1.0/1 | 0.0/0 | all |
| Isaac Okoro | CHI | 21.8/18 | 7.0/4 | 1.0/0 | 1.0/1 | 0.0/0 | 0.0/0 | all |
| Jordan Poole | NOP | 13.9/15 | 6.0/4 | 0.0/2 | 1.0/3 | 0.0/0 | 0.0/0 | all |
| Kelly Oubre Jr. | IND | 20.1/28 | 8.0/4 | 3.0/2 | 0.0/3 | 1.0/1 | 0.0/1 | MIN,AST |
| Zaccharie Risacher | DAL | 9.6/27 | 4.0/4 | 1.0/6 | 0.0/2 | 0.0/5 | 0.0/0 | MIN,REB,STL |
| Micah Potter | POR | 21.2/12 | 7.0/4 | 4.0/3 | 1.0/0 | 0.0/0 | 0.0/0 | MIN |
| Koa Peat | PHX | 0.0/7 | 0.0/4 | 0.0/1 | 0.0/0 | 0.0/0 | 0.0/0 | MIN,PTS |
| Baba Miller | LAC | 0.0/9 | 0.0/4 | 0.0/3 | 0.0/1 | 0.0/0 | 0.0/0 | MIN,PTS,REB,AST |
| Daeqwon Plowden | SAC | 23.9/13 | 10.0/4 | 2.0/2 | 1.0/1 | 0.0/1 | 0.0/0 | MIN |
| Tim Hardaway Jr. | MIA | 18.5/18 | 7.0/3 | 1.0/4 | 1.0/1 | 0.0/1 | 0.0/0 | REB |
| Bones Hyland | MIN | 0.0/4 | 0.0/3 | 0.0/1 | 0.0/0 | 0.0/0 | 0.0/0 | MIN,PTS,REB |
| Jaden Hardy | LAL | 17.7/7 | 7.0/3 | 1.0/2 | 1.0/0 | 0.0/0 | 0.0/0 | all |
| Matisse Thybulle | LAL | 12.5/23 | 3.0/3 | 1.0/3 | 1.0/1 | 1.0/1 | 0.0/1 | MIN |
| Nolan Traore | BKN | 17.9/16 | 7.0/3 | 1.0/2 | 3.0/0 | 0.0/0 | 0.0/0 | all |
| Sion James | CHA | 16.6/27 | 4.0/3 | 2.0/3 | 2.0/0 | 0.0/1 | 0.0/0 | MIN |
| Jakob Poeltl | TOR | 16.5/22 | 10.0/3 | 7.0/6 | 2.0/0 | 1.0/1 | 0.0/1 | MIN |
| Alijah Martin | TOR | 0.0/5 | 0.0/3 | 0.0/0 | 0.0/0 | 0.0/0 | 0.0/0 | MIN,PTS |
| Jaylin Sellers | CHI | 0.0/14 | 0.0/3 | 0.0/1 | 0.0/2 | 0.0/0 | 0.0/0 | MIN,PTS,AST |
| Cam Spencer | MEM | 17.1/16 | 6.0/3 | 1.0/3 | 3.0/2 | 0.0/1 | 0.0/0 | all |
| Kyle Filipowski | UTA | 21.5/9 | 8.0/3 | 6.0/0 | 2.0/0 | 0.0/1 | 0.0/0 | MIN |
| Jarace Walker | IND | 17.2/19 | 6.0/3 | 3.0/6 | 2.0/2 | 0.0/0 | 0.0/1 | all |
| Ben Sheppard | IND | 13.9/12 | 3.0/3 | 1.0/1 | 1.0/0 | 0.0/0 | 0.0/0 | all |
| Reed Sheppard | HOU | 22.1/16 | 9.0/3 | 1.0/2 | 3.0/4 | 1.0/2 | 0.0/0 | MIN |
| Isaiah Crawford | HOU | 0.0/3 | 0.0/3 | 0.0/0 | 0.0/0 | 0.0/0 | 0.0/0 | MIN,PTS |
| Moussa Cissé | DAL | 23.5/2 | 6.0/3 | 8.0/0 | 0.0/0 | 0.0/0 | 1.0/0 | MIN,REB |
| Sidy Cissoko | POR | 0.0/25 | 0.0/3 | 0.0/4 | 0.0/3 | 0.0/0 | 0.0/0 | MIN,PTS,REB,AST |
| Ryan Dunn | PHX | 16.7/14 | 5.0/3 | 3.0/2 | 1.0/0 | 0.0/0 | 0.0/0 | all |
| Jordan Goodwin | PHX | 13.9/22 | 3.0/3 | 3.0/4 | 1.0/0 | 1.0/2 | 0.0/0 | MIN |
| Pat Spencer | PHX | 10.8/7 | 3.0/3 | 1.0/3 | 1.0/1 | 0.0/1 | 0.0/1 | all |
| Jamaree Bouyea | PHX | 0.0/7 | 0.0/3 | 0.0/2 | 0.0/2 | 0.0/0 | 0.0/0 | MIN,PTS,REB,AST |
| Jalen Pickett | LAC | 0.0/2 | 0.0/3 | 0.0/0 | 0.0/0 | 0.0/1 | 0.0/0 | PTS,STL |
| Pelle Larsson | MIA | 23.2/24 | 7.0/2 | 2.0/3 | 2.0/4 | 0.0/1 | 0.0/1 | all |
| Bronny James | LAL | 0.0/7 | 0.0/2 | 0.0/0 | 0.0/0 | 0.0/0 | 0.0/0 | MIN,PTS |
| Chris Mañon | LAL | 0.0/6 | 0.0/2 | 0.0/1 | 0.0/0 | 0.0/0 | 0.0/0 | MIN,PTS |
| Draymond Green | GSW | 21.3/21 | 6.0/2 | 4.0/4 | 4.0/8 | 1.0/1 | 0.0/1 | all |
| Jase Richardson | ORL | 0.0/14 | 0.0/2 | 0.0/2 | 0.0/3 | 0.0/1 | 0.0/2 | MIN,PTS,REB,AST,STL,BLK |
| Khris Middleton | WAS | 13.4/12 | 6.0/2 | 2.0/2 | 2.0/0 | 0.0/0 | 0.0/0 | all |
| Jamal Shead | TOR | 24.9/16 | 7.0/2 | 1.0/2 | 6.0/5 | 1.0/1 | 0.0/0 | MIN |
| Josh Giddey | CHI | 26.5/24 | 14.0/2 | 7.0/7 | 7.0/6 | 1.0/0 | 0.0/0 | PTS |
| Tobe Awaka | CHI | 0.0/14 | 0.0/2 | 0.0/7 | 0.0/2 | 0.0/1 | 0.0/1 | MIN,PTS,REB,AST,STL,BLK |
| Brice Sensabaugh | UTA | 20.2/14 | 8.0/2 | 2.0/2 | 1.0/1 | 0.0/0 | 0.0/0 | all |
| Tari Eason | HOU | 22.3/3 | 8.0/2 | 4.0/1 | 1.0/0 | 1.0/1 | 0.0/0 | MIN |
| Daniel Gafford | DAL | 18.2/22 | 8.0/2 | 5.0/3 | 1.0/1 | 0.0/1 | 0.0/2 | all |
| Robert Williams III | POR | 16.8/15 | 6.0/2 | 6.0/10 | 1.0/1 | 0.0/0 | 1.0/1 | all |
| Khaman Maluach | PHX | 0.0/17 | 0.0/2 | 0.0/6 | 0.0/1 | 0.0/0 | 0.0/1 | MIN,PTS,REB,AST,BLK |
| Kobe Sanders | LAC | 12.5/19 | 5.0/2 | 1.0/0 | 1.0/3 | 0.0/3 | 0.0/0 | STL |
| Keegan Murray | SAC | 20.4/28 | 9.0/2 | 3.0/4 | 1.0/0 | 0.0/1 | 0.0/0 | MIN |
| Trey Lyles | MIN | 20.8/12 | 6.0/1 | 4.0/1 | 1.0/0 | 0.0/0 | 0.0/0 | MIN |
| Jaylen Clark | MIN | 0.0/3 | 0.0/1 | 0.0/1 | 0.0/1 | 0.0/0 | 0.0/0 | MIN,PTS,REB,AST |
| Noa Essengue | CHI | 0.0/10 | 0.0/1 | 0.0/3 | 0.0/0 | 0.0/0 | 0.0/0 | MIN,PTS,REB |
| Vít Krejčí | POR | 0.0/15 | 0.0/1 | 0.0/2 | 0.0/3 | 0.0/2 | 0.0/0 | MIN,PTS,REB,AST,STL |
| Rasheer Fleming | PHX | 0.0/12 | 0.0/1 | 0.0/2 | 0.0/0 | 0.0/1 | 0.0/1 | MIN,PTS,REB,STL,BLK |
| Alex Karaban | SAC | 0.0/5 | 0.0/1 | 0.0/1 | 0.0/0 | 0.0/0 | 0.0/0 | MIN,PTS |
| Simone Fontecchio | MIA | 9.3/3 | 2.0/0 | 1.0/0 | 0.0/0 | 0.0/0 | 0.0/1 | all |
| Ryan Conwell | MIA | 0.0/3 | 0.0/0 | 0.0/0 | 0.0/2 | 0.0/0 | 0.0/0 | MIN,AST |
| Cody Williams | MIN | 29.8/3 | 6.0/0 | 2.0/0 | 1.0/0 | 0.0/0 | 0.0/0 | MIN |
| Isaiah Evans | MIN | 0.0/2 | 0.0/0 | 0.0/1 | 0.0/0 | 0.0/0 | 0.0/0 | all |
| Joan Beringer | MIN | 0.0/14 | 0.0/0 | 0.0/6 | 0.0/1 | 0.0/0 | 0.0/0 | MIN,REB,AST |
| De'Anthony Melton | GSW | 16.2/21 | 6.0/0 | 2.0/2 | 1.0/2 | 1.0/1 | 0.0/0 | all |
| Al Horford | GSW | 14.9/17 | 3.0/0 | 3.0/4 | 1.0/2 | 0.0/1 | 0.0/0 | all |
| Malevy Leons | GSW | 11.1/9 | 2.0/0 | 2.0/1 | 0.0/0 | 0.0/1 | 0.0/0 | all |
| Jamal Cain | ORL | 18.7/14 | 7.0/0 | 3.0/0 | 1.0/0 | 0.0/0 | 0.0/0 | all |
| Nikola Vučević | ORL | 14.1/5 | 7.0/0 | 5.0/1 | 1.0/1 | 0.0/0 | 0.0/0 | all |
| Kingston Flemings | ATL | 0.0/15 | 0.0/0 | 0.0/4 | 0.0/3 | 0.0/0 | 0.0/1 | MIN,REB,AST,BLK |
| Jericho Sims | MIL | 18.9/2 | 4.0/0 | 6.0/0 | 1.0/0 | 0.0/0 | 0.0/0 | MIN,REB |
| Chaney Johnson | BKN | 18.9/5 | 7.0/0 | 5.0/1 | 1.0/0 | 0.0/0 | 0.0/0 | all |
| Christian Anderson | CHA | 0.0/13 | 0.0/0 | 0.0/2 | 0.0/2 | 0.0/2 | 0.0/0 | MIN,REB,AST,STL |
| Liam McNeeley | CHA | 0.0/3 | 0.0/0 | 0.0/1 | 0.0/0 | 0.0/0 | 0.0/0 | MIN |
| Kyle Anderson | TOR | 4.9/5 | 0.0/0 | 0.0/1 | 0.0/2 | 0.0/1 | 0.0/0 | all |
| Jaden Bradley | TOR | 0.0/5 | 0.0/0 | 0.0/0 | 0.0/0 | 0.0/0 | 0.0/0 | MIN |
| Zach Collins | CHI | 17.1/9 | 8.0/0 | 5.0/5 | 1.0/0 | 0.0/0 | 0.0/0 | all |
| Buddy Hield | CHI | 0.0/14 | 0.0/0 | 0.0/2 | 0.0/2 | 0.0/0 | 0.0/0 | MIN,REB,AST |
| Josh Okogie | UTA | 12.5/8 | 3.0/0 | 1.0/1 | 0.0/0 | 0.0/0 | 0.0/0 | all |
| Larry Nance Jr. | IND | 0.0/5 | 0.0/0 | 0.0/0 | 0.0/0 | 0.0/0 | 0.0/0 | MIN |
| Bruce Thornton | HOU | 0.0/2 | 0.0/0 | 0.0/0 | 0.0/0 | 0.0/0 | 0.0/0 | MIN |
| Clint Capela | HOU | 0.0/8 | 0.0/0 | 0.0/3 | 0.0/0 | 0.0/0 | 0.0/0 | MIN,REB |
| Jae'Sean Tate | HOU | 0.0/2 | 0.0/0 | 0.0/0 | 0.0/0 | 0.0/0 | 0.0/0 | all |
| Sergio de Larrea | DAL | 0.0/7 | 0.0/0 | 0.0/2 | 0.0/1 | 0.0/0 | 0.0/0 | MIN,REB,AST |
| Jayson Kent | POR | 0.0/7 | 0.0/0 | 0.0/1 | 0.0/0 | 0.0/1 | 0.0/0 | MIN,STL |
| Collin Gillespie | PHX | 21.0/21 | 6.0/0 | 2.0/1 | 3.0/2 | 1.0/4 | 0.0/0 | STL |
| Cam Christie | LAC | 0.0/2 | 0.0/0 | 0.0/0 | 0.0/0 | 0.0/0 | 0.0/0 | all |
| Nick Martinelli | LAC | 0.0/2 | 0.0/0 | 0.0/1 | 0.0/1 | 0.0/0 | 0.0/0 | AST |
| Jonathan Mogbo | SAC | 0.0/8 | 0.0/0 | 0.0/0 | 0.0/0 | 0.0/0 | 0.0/0 | MIN |

## 2026-10-22

| Metric | Value |
| --- | ---: |
| Games graded | 2 |
| Winner accuracy | 50.0% |
| Spread MAE | 9.50 |
| Total MAE | 25.50 |
| MIN MAE | 7.40 |
| PTS MAE | 4.07 |
| REB MAE | 2.56 |
| AST MAE | 1.22 |
| 10–90 coverage | 85.6% |
| Top picks hit rate | 60.9% (14/23) |
| Top picks avg claimed confidence | 61.4% |

### Games

| Matchup | Pred winner | Actual | Hit | Pred score | Actual score | Pred margin | Act margin | Pred total | Act total |
| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: |
| CLE@PHI | CLE (63%) | PHI | N | CLE 123 – PHI 115 | CLE 106 – PHI 114 | -8.0 | +8.0 | 238.0 | 220.0 |
| DEN@OKC | OKC (65%) | OKC | Y | DEN 102 – OKC 110 | DEN 84 – OKC 96 | +9.0 | +12.0 | 213.0 | 180.0 |

### Top confident picks

| Player | Matchup | Stat | Range | Actual | Hit |
| --- | --- | --- | --- | ---: | --- |
| player:1642845 | PHI vs CLE | AST | 2-6 | 6 | Y |
| player:1630178 | PHI vs CLE | REB | 3-7 | 3 | Y |
| player:1642845 | PHI vs CLE | REB | 3-7 | 7 | Y |
| player:1627936 | OKC vs DEN | STL | 1-3 | 1 | Y |
| player:1628378 | CLE vs PHI | STL | 1-3 | 2 | Y |
| player:1628983 | OKC vs DEN | STL | 1-3 | 0 | N |
| player:1628983 | OKC vs DEN | REB | 3-7 | 2 | N |
| player:1630178 | PHI vs CLE | STL | 1-3 | 2 | Y |
| player:1627750 | DEN vs OKC | REB | 4-8 | 10 | N |
| player:1630596 | CLE vs PHI | BLK | 1-3 | 0 | N |
| player:1628378 | CLE vs PHI | REB | 3-7 | 10 | N |
| player:201935 | CLE vs PHI | REB | 3-7 | 3 | Y |
| player:1631096 | OKC vs DEN | BLK | 1-3 | 4 | N |
| player:203954 | PHI vs CLE | AST | 2-6 | 1 | N |
| player:203932 | DEN vs OKC | REB | 4-8 | 6 | Y |
| player:1630596 | CLE vs PHI | AST | 2-6 | 2 | Y |
| player:202331 | PHI vs CLE | STL | 1-3 | 0 | N |
| player:1628378 | CLE vs PHI | AST | 3-7 | 3 | Y |
| player:1628983 | OKC vs DEN | AST | 3-7 | 3 | Y |
| player:1627750 | DEN vs OKC | AST | 3-7 | 3 | Y |
| player:1630178 | PHI vs CLE | AST | 3-7 | 6 | Y |
| player:203999 | DEN vs OKC | AST | 5-9 | 5 | Y |
| player:1631096 | OKC vs DEN | REB | 5-9 | 17 | N |

### Player grades (MIN / PTS / REB / AST / STL / BLK)

| Player | Team | MIN pred/act | PTS | REB | AST | STL | BLK | in 10–90 (any miss listed) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Tyrese Maxey | PHI | 32.9/42 | 18.0/32 | 2.0/3 | 5.0/6 | 1.0/2 | 0.0/0 | MIN |
| Donovan Mitchell | CLE | 37.1/35 | 21.0/32 | 3.0/10 | 5.0/3 | 1.0/2 | 0.0/1 | REB |
| Joel Embiid | PHI | 27.3/34 | 18.0/24 | 7.0/7 | 3.0/1 | 0.0/0 | 1.0/0 | MIN |
| Jaylen Brown | PHI | 19.5/38 | 3.0/21 | 2.0/8 | 1.0/4 | 0.0/1 | 0.0/0 | all |
| Jalen Williams | OKC | 20.3/33 | 10.0/21 | 3.0/5 | 3.0/3 | 1.0/0 | 0.0/0 | MIN |
| Aaron Gordon | DEN | 25.4/29 | 11.0/20 | 5.0/6 | 2.0/1 | 0.0/2 | 0.0/1 | all |
| Evan Mobley | CLE | 37.2/34 | 15.0/18 | 10.0/8 | 4.0/2 | 1.0/0 | 1.0/0 | all |
| LeBron James | PHI | 27.4/33 | 5.0/17 | 4.0/10 | 2.0/5 | 0.0/3 | 0.0/1 | all |
| Shai Gilgeous-Alexander | OKC | 32.6/35 | 17.0/17 | 2.0/2 | 5.0/3 | 1.0/0 | 0.0/1 | all |
| James Harden | CLE | 37.5/33 | 18.0/16 | 4.0/3 | 6.0/5 | 1.0/1 | 0.0/0 | MIN |
| Jarrett Allen | CLE | 31.6/28 | 14.0/14 | 10.0/7 | 2.0/0 | 1.0/0 | 1.0/2 | all |
| Nikola Jokić | DEN | 34.2/35 | 17.0/13 | 10.0/7 | 7.0/5 | 1.0/1 | 0.0/1 | all |
| DeMar DeRozan | DEN | 20.3/28 | 11.0/13 | 2.0/2 | 2.0/0 | 0.0/0 | 0.0/0 | MIN |
| Chet Holmgren | OKC | 26.9/28 | 12.0/12 | 7.0/17 | 1.0/2 | 0.0/1 | 1.0/4 | REB,BLK |
| Ajay Mitchell | OKC | 22.3/23 | 8.0/12 | 1.0/0 | 2.0/0 | 1.0/5 | 0.0/1 | STL |
| VJ Edgecombe | PHI | 29.9/33 | 10.0/11 | 3.0/7 | 3.0/6 | 1.0/3 | 0.0/0 | all |
| Mario Hezonja | CLE | 0.0/19 | 0.0/10 | 0.0/3 | 0.0/2 | 0.0/2 | 0.0/1 | MIN,PTS,REB,AST,STL,BLK |
| Cason Wallace | OKC | 23.2/24 | 5.0/9 | 2.0/1 | 2.0/1 | 1.0/4 | 0.0/0 | all |
| Peyton Watson | CLE | 20.0/30 | 7.0/8 | 2.0/1 | 1.0/2 | 0.0/2 | 0.0/1 | MIN |
| Alex Caruso | OKC | 24.9/20 | 7.0/7 | 2.0/4 | 2.0/5 | 1.0/1 | 0.0/1 | all |
| Christian Braun | DEN | 26.5/33 | 7.0/7 | 3.0/6 | 2.0/1 | 0.0/1 | 0.0/0 | all |
| Isaiah Hartenstein | OKC | 20.1/23 | 8.0/6 | 9.0/6 | 3.0/2 | 1.0/0 | 0.0/1 | all |
| Jamal Murray | DEN | 34.4/37 | 15.0/6 | 3.0/10 | 5.0/3 | 1.0/1 | 0.0/0 | REB |
| Sam Merrill | CLE | 22.3/24 | 8.0/5 | 1.0/5 | 2.0/2 | 0.0/1 | 0.0/0 | REB |
| Cameron Johnson | DEN | 29.7/11 | 11.0/5 | 3.0/2 | 2.0/1 | 1.0/0 | 0.0/0 | MIN |
| Ryan Nembhard | DEN | 27.8/2 | 7.0/5 | 2.0/1 | 4.0/1 | 0.0/0 | 0.0/0 | MIN |
| Jared McCain | OKC | 22.5/18 | 9.0/4 | 1.0/0 | 1.0/1 | 0.0/0 | 0.0/0 | all |
| Alpha Diallo | DEN | 0.0/22 | 0.0/4 | 0.0/2 | 0.0/3 | 0.0/1 | 0.0/0 | MIN,PTS,REB,AST,STL |
| Trevon Brazile | DEN | 0.0/18 | 0.0/4 | 0.0/12 | 0.0/0 | 0.0/0 | 0.0/0 | MIN,PTS,REB |
| Kentavious Caldwell-Pope | PHI | 0.0/25 | 0.0/3 | 0.0/3 | 0.0/2 | 0.0/1 | 0.0/0 | all |
| Jaylon Tyson | CLE | 12.1/24 | 5.0/3 | 2.0/6 | 1.0/2 | 0.0/1 | 0.0/2 | MIN,BLK |
| Jaylin Williams | OKC | 19.1/15 | 12.0/3 | 5.0/7 | 2.0/3 | 0.0/0 | 0.0/0 | all |
| Kenrich Williams | OKC | 6.9/6 | 0.0/3 | 1.0/1 | 0.0/1 | 0.0/0 | 0.0/0 | all |
| DaRon Holmes II | DEN | 0.0/2 | 0.0/3 | 0.0/1 | 0.0/1 | 0.0/0 | 0.0/0 | PTS,AST |
| Anfernee Simons | PHI | 0.0/17 | 0.0/2 | 0.0/3 | 0.0/0 | 0.0/0 | 0.0/0 | all |
| Adem Bona | PHI | 19.1/14 | 6.0/2 | 5.0/2 | 0.0/0 | 0.0/0 | 1.0/1 | all |
| Jabari Walker | PHI | 0.0/4 | 0.0/2 | 0.0/1 | 0.0/0 | 0.0/0 | 0.0/0 | MIN,PTS |
| Aday Mara | OKC | 9.5/13 | 2.0/2 | 0.0/3 | 0.0/0 | 0.0/1 | 0.0/1 | REB,STL |
| Marvin Bagley III | DEN | 17.2/11 | 8.0/2 | 5.0/3 | 0.0/1 | 0.0/0 | 0.0/0 | all |
| Tyus Jones | DEN | 0.0/10 | 0.0/2 | 0.0/0 | 0.0/0 | 0.0/1 | 0.0/0 | MIN,PTS,STL |
| Tyrese Proctor | CLE | 1.1/5 | 0.0/0 | 0.0/0 | 0.0/0 | 0.0/0 | 0.0/0 | all |
| Craig Porter Jr. | CLE | 2.6/8 | 0.0/0 | 0.0/3 | 0.0/0 | 0.0/1 | 0.0/0 | all |
| Brooks Barnhizer | OKC | 9.6/2 | 0.0/0 | 1.0/0 | 0.0/1 | 0.0/0 | 0.0/0 | all |
| Bennett Stirtz | OKC | 0.0/2 | 0.0/0 | 0.0/0 | 0.0/0 | 0.0/0 | 0.0/0 | all |
| Bryce Hopkins | DEN | 0.0/2 | 0.0/0 | 0.0/1 | 0.0/0 | 0.0/0 | 0.0/0 | all |

## 2026-10-23

| Metric | Value |
| --- | ---: |
| Games graded | 12 |
| Winner accuracy | 58.3% |
| Spread MAE | 12.29 |
| Total MAE | 13.58 |
| MIN MAE | 7.50 |
| PTS MAE | 5.23 |
| REB MAE | 2.19 |
| AST MAE | 1.29 |
| 10–90 coverage | 77.8% |
| Top picks hit rate | 67.7% (21/31) |
| Top picks avg claimed confidence | 57.6% |

### Games

| Matchup | Pred winner | Actual | Hit | Pred score | Actual score | Pred margin | Act margin | Pred total | Act total |
| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: |
| NYK@BOS | BOS (63%) | BOS | Y | NYK 102 – BOS 109 | NYK 103 – BOS 107 | +8.0 | +4.0 | 212.0 | 210.0 |
| HOU@SAS | HOU (57%) | HOU | Y | HOU 111 – SAS 107 | HOU 114 – SAS 110 | -5.0 | -4.0 | 218.0 | 224.0 |
| ATL@CHA | CHA (69%) | ATL | N | ATL 107 – CHA 118 | ATL 128 – CHA 81 | +11.0 | -47.0 | 226.0 | 209.0 |
| DAL@IND | DAL (52%) | DAL | Y | DAL 110 – IND 108 | DAL 121 – IND 105 | -2.0 | -16.0 | 218.0 | 226.0 |
| MIN@ORL | ORL (55%) | MIN | N | MIN 111 – ORL 114 | MIN 115 – ORL 93 | +4.0 | -22.0 | 226.0 | 208.0 |
| TOR@WAS | TOR (70%) | TOR | Y | TOR 121 – WAS 109 | TOR 112 – WAS 102 | -12.0 | -10.0 | 230.0 | 214.0 |
| DET@MIA | DET (55%) | DET | Y | DET 115 – MIA 112 | DET 128 – MIA 111 | -4.0 | -17.0 | 226.0 | 239.0 |
| CHI@MIL | MIL (59%) | CHI | N | CHI 115 – MIL 120 | CHI 132 – MIL 125 | +6.0 | -7.0 | 235.0 | 257.0 |
| NOP@UTA | NOP (55%) | UTA | N | NOP 114 – UTA 111 | NOP 119 – UTA 120 | -3.0 | +1.0 | 224.0 | 239.0 |
| MEM@GSW | GSW (58%) | MEM | N | MEM 106 – GSW 110 | MEM 111 – GSW 108 | +5.0 | -3.0 | 216.0 | 219.0 |
| LAC@LAL | LAL (62%) | LAL | Y | LAC 112 – LAL 118 | LAC 117 – LAL 125 | +7.0 | +8.0 | 230.0 | 242.0 |
| POR@SAC | POR (70%) | POR | Y | POR 114 – SAC 102 | POR 128 – SAC 120 | -11.5 | -8.0 | 217.0 | 248.0 |

### Top confident picks

| Player | Matchup | Stat | Range | Actual | Hit |
| --- | --- | --- | --- | ---: | --- |
| player:1631157 | MIL vs CHI | AST | 2-6 | 6 | Y |
| player:1629639 | MIL vs CHI | AST | 2-6 | 4 | Y |
| player:1626167 | MIL vs CHI | REB | 3-7 | 3 | Y |
| player:1631157 | MIL vs CHI | REB | 4-8 | 7 | Y |
| player:1631159 | CHI vs MIL | REB | 5-9 | 3 | N |
| player:1630581 | CHI vs MIL | AST | 5-9 | 9 | Y |
| player:1630581 | CHI vs MIL | REB | 5-9 | 4 | N |
| player:1631170 | MIL vs CHI | REB | 6-10 | 11 | N |
| player:1628976 | ORL vs MIN | STL | 1-3 | 0 | N |
| player:1628973 | NYK vs BOS | AST | 2-6 | 4 | Y |
| player:1627739 | LAC vs LAL | STL | 1-3 | 2 | Y |
| player:1630183 | MIN vs ORL | STL | 1-3 | 0 | N |
| player:1630217 | ORL vs MIN | AST | 2-6 | 0 | N |
| player:1642852 | NOP vs UTA | AST | 2-6 | 2 | Y |
| player:1628389 | MIA vs DET | AST | 2-6 | 3 | Y |
| player:203507 | MIA vs DET | AST | 2-6 | 5 | Y |
| player:1641708 | HOU vs SAS | AST | 3-7 | 4 | Y |
| player:1628368 | SAS vs HOU | AST | 3-7 | 9 | N |
| player:1627832 | HOU vs SAS | AST | 3-7 | 5 | Y |
| player:1642264 | SAS vs HOU | AST | 3-7 | 5 | Y |
| player:202699 | SAS vs HOU | REB | 3-7 | 0 | N |
| player:1630578 | HOU vs SAS | AST | 4-8 | 7 | Y |
| player:1641705 | SAS vs HOU | BLK | 2-4 | 2 | Y |
| player:201142 | HOU vs SAS | AST | 2-6 | 6 | Y |
| player:1630591 | ORL vs MIN | STL | 1-3 | 1 | Y |
| player:1628404 | NYK vs BOS | AST | 2-6 | 5 | Y |
| player:1628369 | BOS vs NYK | AST | 2-6 | 7 | N |
| player:1641709 | DET vs MIA | STL | 1-3 | 1 | Y |
| player:1641764 | GSW vs MEM | AST | 2-6 | 3 | Y |
| player:1630591 | ORL vs MIN | AST | 2-6 | 6 | Y |
| player:201950 | POR vs SAC | AST | 2-6 | 8 | N |

### Player grades (MIN / PTS / REB / AST / STL / BLK)

| Player | Team | MIN pred/act | PTS | REB | AST | STL | BLK | in 10–90 (any miss listed) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Jayson Tatum | BOS | 31.1/37 | 16.0/36 | 6.0/9 | 4.0/7 | 1.0/3 | 0.0/0 | MIN,PTS,STL |
| Giannis Antetokounmpo | MIA | 26.7/33 | 18.0/36 | 8.0/12 | 3.0/5 | 1.0/2 | 0.0/1 | MIN |
| Tyler Herro | MIL | 26.6/32 | 15.0/34 | 3.0/5 | 3.0/4 | 0.0/1 | 0.0/0 | PTS |
| Darius Acuff Jr. | SAC | 29.7/37 | 17.0/33 | 4.0/2 | 2.0/4 | 2.0/0 | 0.0/0 | MIN |
| Alperen Sengun | HOU | 30.9/36 | 17.0/29 | 10.0/7 | 5.0/7 | 1.0/0 | 0.0/1 | all |
| Scottie Barnes | TOR | 28.8/37 | 14.0/28 | 6.0/14 | 6.0/5 | 1.0/2 | 0.0/2 | MIN,REB |
| Ty Jerome | MEM | 23.3/32 | 13.0/28 | 2.0/2 | 3.0/5 | 1.0/1 | 0.0/0 | MIN |
| Austin Reaves | LAL | 33.2/38 | 15.0/28 | 3.0/2 | 5.0/9 | 1.0/2 | 0.0/0 | all |
| Domantas Sabonis | SAC | 25.1/39 | 12.0/27 | 10.0/19 | 4.0/10 | 1.0/0 | 0.0/0 | MIN,REB,AST |
| Darius Garland | LAC | 27.1/37 | 14.0/26 | 1.0/0 | 5.0/6 | 1.0/1 | 0.0/0 | MIN |
| Deni Avdija | POR | 25.8/38 | 14.0/26 | 5.0/7 | 4.0/6 | 1.0/1 | 0.0/0 | MIN |
| Victor Wembanyama | SAS | 32.7/32 | 18.0/25 | 11.0/13 | 3.0/2 | 1.0/0 | 1.0/2 | all |
| Norman Powell | CHI | 18.6/33 | 11.0/25 | 2.0/4 | 1.0/1 | 1.0/0 | 0.0/0 | MIN |
| Cameron Boozer | MEM | 28.0/37 | 6.0/25 | 8.0/13 | 1.0/6 | 0.0/2 | 0.0/0 | MIN,PTS,AST,STL |
| Kyrie Irving | DAL | 22.8/25 | 13.0/24 | 2.0/1 | 3.0/3 | 1.0/1 | 0.0/1 | all |
| Jaren Jackson Jr. | UTA | 23.8/33 | 15.0/24 | 4.0/10 | 1.0/3 | 1.0/0 | 1.0/3 | MIN,REB,BLK |
| Stephen Curry | GSW | 25.6/30 | 16.0/24 | 3.0/2 | 3.0/4 | 1.0/0 | 0.0/0 | all |
| Pascal Siakam | IND | 27.4/29 | 15.0/23 | 4.0/3 | 3.0/3 | 1.0/0 | 0.0/0 | all |
| RJ Barrett | TOR | 28.8/34 | 15.0/23 | 4.0/9 | 4.0/4 | 0.0/0 | 0.0/1 | all |
| John Collins | DET | 19.7/29 | 10.0/23 | 4.0/7 | 0.0/1 | 0.0/0 | 0.0/0 | MIN |
| Zion Williamson | NOP | 25.0/33 | 15.0/23 | 4.0/5 | 3.0/2 | 1.0/3 | 0.0/0 | MIN |
| Luka Dončić | LAL | 29.1/37 | 19.0/23 | 6.0/6 | 5.0/7 | 1.0/0 | 0.0/1 | MIN |
| Karl-Anthony Towns | NYK | 25.3/37 | 15.0/22 | 10.0/10 | 2.0/3 | 1.0/0 | 0.0/0 | MIN |
| Trae Young | WAS | 24.2/37 | 15.0/22 | 1.0/1 | 4.0/12 | 1.0/1 | 0.0/0 | MIN,AST |
| Walker Kessler | LAL | 28.2/35 | 10.0/22 | 11.0/8 | 1.0/3 | 0.0/3 | 1.0/6 | MIN,STL,BLK |
| Brook Lopez | LAC | 26.1/20 | 10.0/22 | 5.0/4 | 2.0/0 | 1.0/0 | 1.0/3 | MIN,BLK |
| Zach LaVine | SAC | 24.0/39 | 13.0/22 | 1.0/5 | 2.0/1 | 0.0/2 | 0.0/1 | MIN,REB |
| Caleb Wilson | CHI | 27.3/33 | 11.0/21 | 3.0/6 | 0.0/1 | 2.0/1 | 0.0/2 | MIN |
| OG Anunoby | NYK | 32.0/34 | 11.0/20 | 3.0/10 | 1.0/8 | 1.0/0 | 0.0/0 | REB,AST |
| Miles McBride | NYK | 13.1/30 | 3.0/20 | 0.5/2 | 1.0/1 | 0.0/1 | 0.0/0 | MIN,PTS |
| Dylan Harper | SAS | 27.6/36 | 10.0/20 | 3.0/3 | 3.0/2 | 1.0/0 | 0.0/0 | MIN |
| Amen Thompson | HOU | 34.6/36 | 13.0/20 | 6.0/10 | 5.0/4 | 1.0/2 | 0.0/2 | all |
| Kevin Durant | HOU | 33.1/37 | 19.0/20 | 4.0/7 | 4.0/6 | 0.0/0 | 1.0/0 | all |
| P.J. Washington | DAL | 26.1/33 | 9.0/20 | 5.0/13 | 2.0/0 | 1.0/0 | 0.0/3 | MIN,REB,BLK |
| Wendell Carter Jr. | ORL | 29.5/29 | 11.0/20 | 9.0/9 | 2.0/1 | 1.0/0 | 0.0/2 | all |
| Tre Johnson | WAS | 0.0/26 | 0.0/20 | 0.0/2 | 0.0/0 | 0.0/1 | 0.0/0 | MIN,PTS,REB,STL |
| Saddiq Bey | NOP | 25.1/22 | 10.0/20 | 3.0/3 | 2.0/1 | 0.0/0 | 0.0/1 | all |
| Jalen Brunson | NYK | 35.2/37 | 16.0/19 | 1.0/2 | 5.0/4 | 1.0/0 | 0.0/2 | BLK |
| De'Aaron Fox | SAS | 30.5/34 | 13.0/19 | 2.0/4 | 5.0/9 | 1.0/2 | 0.0/0 | all |
| Jalen Johnson | ATL | 27.3/29 | 13.0/19 | 7.0/7 | 4.0/8 | 1.0/3 | 0.0/1 | STL |
| Aaron Wiggins | ATL | 14.0/22 | 6.0/19 | 2.0/1 | 0.0/1 | 0.0/2 | 0.0/0 | MIN,PTS |
| Paul Reed | DET | 11.4/26 | 5.0/19 | 3.0/11 | 1.0/3 | 0.0/0 | 0.0/0 | MIN,PTS,REB |
| Jaime Jaquez Jr. | MIL | 27.4/35 | 12.0/19 | 5.0/11 | 2.0/5 | 1.0/0 | 0.0/0 | MIN,REB |
| Leonard Miller | CHI | 26.7/24 | 10.0/19 | 8.0/3 | 1.0/2 | 1.0/0 | 0.0/1 | all |
| Keyonte George | UTA | 23.2/32 | 11.0/19 | 1.0/1 | 4.0/10 | 0.0/1 | 0.0/0 | MIN,AST |
| Toumani Camara | POR | 25.0/27 | 8.0/19 | 3.0/2 | 2.0/1 | 1.0/2 | 0.0/0 | all |
| Damian Lillard | POR | 19.9/33 | 12.0/19 | 2.0/5 | 3.0/2 | 0.0/2 | 0.0/0 | MIN |
| Tyrese Haliburton | IND | 22.7/32 | 11.0/18 | 2.0/6 | 5.0/7 | 1.0/1 | 0.0/2 | MIN,REB,BLK |
| Franz Wagner | ORL | 25.6/33 | 14.0/18 | 4.0/6 | 3.0/5 | 1.0/1 | 0.0/0 | MIN |
| Davion Mitchell | MIA | 32.2/33 | 7.0/18 | 1.0/2 | 6.0/5 | 1.0/0 | 0.0/2 | PTS,BLK |
| Brandin Podziemski | GSW | 30.2/33 | 10.0/18 | 5.0/2 | 4.0/3 | 1.0/3 | 0.0/1 | all |
| Yaxel Lendeborg | GSW | 25.9/37 | 7.0/18 | 2.0/13 | 1.0/6 | 1.0/3 | 0.0/0 | MIN,PTS,REB,AST,STL |
| Naz Reid | CHA | 26.7/25 | 11.0/17 | 6.0/6 | 2.0/2 | 1.0/1 | 0.0/0 | all |
| Duncan Robinson | DET | 23.1/28 | 9.0/17 | 1.0/1 | 2.0/2 | 0.0/2 | 0.0/0 | all |
| Jaxson Hayes | UTA | 18.6/26 | 6.0/17 | 3.0/5 | 0.0/2 | 0.0/0 | 0.0/1 | MIN,PTS |
| Jaylen Wells | MEM | 21.2/25 | 8.0/17 | 2.0/4 | 2.0/3 | 1.0/0 | 0.0/0 | all |
| Andrew Nembhard | IND | 28.3/32 | 11.0/16 | 1.0/2 | 5.0/5 | 1.0/1 | 0.0/0 | all |
| Max Christie | DAL | 22.4/38 | 7.0/16 | 1.0/4 | 2.0/4 | 0.0/1 | 0.0/0 | MIN |
| Kawhi Leonard | TOR | 25.9/28 | 22.0/16 | 7.0/9 | 2.0/1 | 2.0/3 | 0.0/0 | all |
| Cade Cunningham | DET | 33.1/30 | 19.0/16 | 4.0/2 | 7.0/8 | 1.0/1 | 0.0/3 | BLK |
| Lauri Markkanen | UTA | 26.8/34 | 12.0/16 | 3.0/6 | 1.0/3 | 0.0/1 | 0.0/0 | MIN |
| Dejounte Murray | NOP | 25.6/30 | 12.0/16 | 4.0/6 | 5.0/6 | 1.0/3 | 0.0/0 | MIN |
| Rui Hachimura | LAC | 31.4/33 | 12.0/16 | 5.0/6 | 1.0/1 | 1.0/2 | 0.0/0 | all |
| Derrick Jones Jr. | LAC | 21.7/35 | 8.0/16 | 3.0/4 | 1.0/1 | 1.0/2 | 0.0/0 | MIN |
| Paul George | BOS | 28.4/34 | 14.0/15 | 4.0/7 | 2.0/2 | 1.0/2 | 0.0/0 | all |
| Neemias Queta | BOS | 21.0/22 | 7.0/15 | 6.0/6 | 1.0/1 | 0.0/0 | 0.0/3 | BLK |
| Stephon Castle | SAS | 26.9/33 | 12.0/15 | 3.0/7 | 5.0/5 | 1.0/1 | 0.0/0 | MIN |
| Naji Marshall | DAL | 23.6/33 | 9.0/15 | 2.0/4 | 3.0/6 | 1.0/3 | 0.0/0 | MIN,STL |
| Anthony Edwards | MIN | 28.9/33 | 15.0/15 | 3.0/4 | 3.0/4 | 1.0/4 | 0.0/0 | STL |
| Jaden McDaniels | MIN | 25.3/30 | 9.0/15 | 3.0/6 | 2.0/3 | 1.0/0 | 0.0/2 | all |
| Daniss Jenkins | DET | 22.7/22 | 9.0/15 | 2.0/5 | 4.0/5 | 1.0/1 | 0.0/0 | all |
| Darryn Peterson | UTA | 27.4/30 | 10.0/15 | 4.0/3 | 3.0/1 | 0.0/0 | 0.0/0 | all |
| Sidy Cissoko | POR | 13.1/26 | 2.0/15 | 1.0/7 | 1.0/1 | 0.0/1 | 0.0/0 | MIN,PTS,REB |
| Fred VanVleet | HOU | 31.6/32 | 10.0/14 | 2.0/3 | 5.0/5 | 1.0/3 | 0.0/0 | all |
| Nickeil Alexander-Walker | ATL | 27.5/27 | 11.0/14 | 2.0/3 | 2.0/5 | 1.0/2 | 0.0/0 | all |
| Cooper Flagg | DAL | 24.2/17 | 11.0/14 | 3.0/5 | 3.0/6 | 1.0/3 | 0.0/1 | MIN,STL |
| Paolo Banchero | ORL | 35.4/26 | 18.0/14 | 6.0/6 | 5.0/5 | 1.0/1 | 0.0/0 | MIN |
| Jalen Suggs | ORL | 30.6/34 | 12.0/14 | 3.0/6 | 4.0/6 | 2.0/1 | 0.0/1 | all |
| Rudy Gobert | MIN | 24.5/30 | 9.0/14 | 10.0/9 | 2.0/1 | 1.0/0 | 1.0/0 | all |
| Ayo Dosunmu | MIN | 24.1/27 | 9.0/14 | 2.0/7 | 2.0/10 | 1.0/1 | 0.0/1 | REB,AST |
| Kyle Kuzma | MIL | 21.0/30 | 10.0/14 | 4.0/9 | 2.0/4 | 0.0/0 | 0.0/0 | MIN |
| Jalen Smith | CHI | 15.6/24 | 7.0/14 | 6.0/13 | 1.0/1 | 0.0/3 | 0.0/0 | MIN,STL |
| Ziaire Williams | LAL | 21.8/31 | 8.0/14 | 3.0/5 | 1.0/0 | 1.0/2 | 0.0/1 | MIN |
| Precious Achiuwa | SAC | 26.0/26 | 8.0/14 | 6.0/6 | 1.0/1 | 1.0/2 | 0.0/0 | all |
| CJ McCollum | ATL | 24.2/22 | 13.0/13 | 2.0/1 | 2.0/2 | 0.0/0 | 0.0/1 | all |
| Obi Toppin | IND | 0.0/25 | 0.0/13 | 0.0/5 | 0.0/1 | 0.0/0 | 0.0/1 | MIN,PTS,REB,BLK |
| Terrence Shannon Jr | MIN | 18.8/22 | 6.0/13 | 1.0/4 | 1.0/1 | 0.0/0 | 0.0/1 | REB |
| Buddy Hield | CHI | 0.0/15 | 0.0/13 | 0.0/2 | 0.0/2 | 0.0/1 | 0.0/0 | MIN,PTS,REB,AST,STL |
| Quentin Grimes | LAL | 21.4/31 | 7.0/13 | 2.0/8 | 2.0/4 | 0.0/1 | 0.0/0 | MIN,REB |
| Matisse Thybulle | LAL | 15.5/24 | 3.0/13 | 1.0/1 | 1.0/2 | 1.0/2 | 0.0/1 | MIN |
| Keaton Wagler | LAC | 25.3/24 | 10.0/13 | 3.0/3 | 3.0/3 | 1.0/1 | 0.0/0 | all |
| Robert Williams III | POR | 16.9/18 | 6.0/13 | 6.0/6 | 1.0/0 | 0.0/0 | 0.0/1 | all |
| Derrick White | BOS | 31.6/33 | 15.0/12 | 3.0/4 | 5.0/6 | 1.0/1 | 0.0/0 | all |
| Tari Eason | HOU | 0.0/27 | 0.0/12 | 0.0/6 | 0.0/0 | 0.0/3 | 0.0/0 | MIN,PTS,REB,STL |
| LaMelo Ball | MIN | 25.4/23 | 14.0/12 | 3.0/5 | 4.0/5 | 1.0/2 | 0.0/0 | all |
| Immanuel Quickley | TOR | 20.3/29 | 10.0/12 | 2.0/1 | 5.0/6 | 1.0/0 | 0.0/0 | MIN |
| Isaiah Joe | DET | 10.7/18 | 3.0/12 | 0.0/3 | 0.0/1 | 0.0/0 | 0.0/0 | MIN |
| Myles Turner | MIL | 23.2/30 | 12.0/12 | 6.0/3 | 1.0/1 | 0.0/0 | 1.0/5 | MIN,BLK |
| Isaac Okoro | CHI | 19.6/28 | 6.0/12 | 1.0/3 | 1.0/1 | 0.0/0 | 0.0/1 | MIN |
| Derik Queen | NOP | 24.7/29 | 10.0/12 | 6.0/7 | 3.0/2 | 1.0/2 | 0.0/2 | all |
| Jordan Poole | NOP | 0.0/19 | 0.0/12 | 0.0/2 | 0.0/2 | 0.0/3 | 0.0/1 | MIN,PTS,REB,AST,STL,BLK |
| Keegan Murray | SAC | 22.4/26 | 7.0/12 | 3.0/2 | 1.0/1 | 0.0/1 | 0.0/0 | all |
| Jrue Holiday | POR | 26.8/26 | 10.0/12 | 3.0/1 | 4.0/8 | 1.0/1 | 0.0/1 | all |
| Ja Morant | POR | 22.9/27 | 13.0/12 | 2.0/3 | 4.0/7 | 1.0/1 | 0.0/0 | all |
| Grayson Allen | CHA | 19.4/20 | 8.0/11 | 1.0/2 | 1.0/3 | 0.0/0 | 0.0/0 | all |
| Tidjane Salaün | CHA | 0.0/23 | 0.0/11 | 0.0/5 | 0.0/1 | 0.0/2 | 0.0/0 | MIN,PTS,REB,AST,STL |
| Dyson Daniels | ATL | 24.2/23 | 7.0/11 | 4.0/9 | 3.0/4 | 2.0/7 | 0.0/1 | REB,STL |
| Corey Kispert | ATL | 11.2/10 | 4.0/11 | 1.0/1 | 0.0/1 | 0.0/0 | 0.0/0 | all |
| Zaccharie Risacher | DAL | 15.1/32 | 6.0/11 | 2.0/6 | 0.0/1 | 1.0/1 | 0.0/3 | MIN,BLK |
| Jonathan Kuminga | MIN | 22.0/27 | 10.0/11 | 4.0/8 | 1.0/5 | 1.0/1 | 0.0/0 | AST |
| Bilal Coulibaly | WAS | 21.8/26 | 8.0/11 | 3.0/6 | 2.0/0 | 1.0/0 | 0.0/1 | all |
| Kyshawn George | WAS | 20.1/26 | 9.0/11 | 3.0/3 | 2.0/3 | 1.0/2 | 0.0/0 | MIN |
| Bobby Portis Jr. | MIA | 22.8/21 | 9.0/11 | 5.0/8 | 1.0/2 | 0.0/1 | 0.0/0 | all |
| Ryan Rollins | MIL | 24.7/34 | 11.0/11 | 3.0/7 | 4.0/6 | 1.0/1 | 0.0/1 | MIN,REB |
| AJ Green | MIL | 24.6/17 | 8.0/11 | 2.0/1 | 2.0/0 | 0.0/0 | 0.0/0 | MIN |
| Kel'el Ware | MIL | 20.0/15 | 8.0/11 | 9.0/4 | 0.0/0 | 1.0/0 | 0.0/0 | all |
| Tre Jones | CHI | 19.2/24 | 8.0/11 | 2.0/3 | 4.0/8 | 1.0/2 | 0.0/0 | all |
| Cam Spencer | MEM | 0.0/17 | 0.0/11 | 0.0/2 | 0.0/1 | 0.0/0 | 0.0/0 | MIN,PTS,REB |
| Josh Hart | NYK | 30.2/36 | 8.0/10 | 7.0/12 | 4.0/5 | 1.0/3 | 0.0/0 | all |
| Devin Vassell | SAS | 31.0/36 | 9.0/10 | 2.0/4 | 2.0/2 | 1.0/3 | 0.0/0 | all |
| Onyeka Okongwu | ATL | 26.9/22 | 11.0/10 | 7.0/4 | 2.0/1 | 1.0/0 | 0.0/0 | all |
| Isaiah Collier | UTA | 20.5/18 | 6.0/10 | 1.0/2 | 5.0/7 | 1.0/0 | 0.0/0 | all |
| Brice Sensabaugh | UTA | 18.6/16 | 7.0/10 | 1.0/3 | 1.0/2 | 0.0/0 | 0.0/1 | all |
| De'Anthony Melton | GSW | 20.7/20 | 8.0/10 | 3.0/1 | 2.0/0 | 1.0/1 | 0.0/1 | all |
| Graham Ike | GSW | 0.0/12 | 0.0/10 | 0.0/2 | 0.0/1 | 0.0/1 | 0.0/0 | MIN,PTS,AST,STL |
| Luguentz Dort | ATL | 19.2/19 | 6.0/9 | 2.0/5 | 0.0/2 | 1.0/1 | 0.0/0 | all |
| Aaron Nesmith | IND | 27.5/20 | 10.0/9 | 3.0/4 | 1.0/1 | 1.0/0 | 0.0/0 | MIN |
| Ivica Zubac | IND | 24.3/24 | 12.0/9 | 10.0/11 | 1.0/2 | 0.0/0 | 0.0/1 | all |
| Trey Lyles | MIN | 17.5/17 | 4.0/9 | 3.0/6 | 0.0/2 | 0.0/0 | 0.0/0 | all |
| Joan Beringer | MIN | 0.0/15 | 0.0/9 | 0.0/9 | 0.0/0 | 0.0/0 | 0.0/0 | MIN,PTS,REB |
| Anthony Davis | WAS | 28.9/32 | 17.0/9 | 10.0/9 | 1.0/0 | 1.0/1 | 1.0/2 | all |
| Trey Murphy III | NOP | 27.8/31 | 12.0/9 | 2.0/6 | 3.0/3 | 1.0/1 | 0.0/0 | all |
| Luka Garza | BOS | 0.0/4 | 0.0/8 | 0.0/1 | 0.0/0 | 0.0/1 | 0.0/0 | MIN,PTS,STL |
| Landry Shamet | NYK | 21.1/21 | 6.0/8 | 1.0/2 | 1.0/0 | 0.0/0 | 0.0/0 | all |
| Keldon Johnson | SAS | 16.6/19 | 7.0/8 | 3.0/6 | 1.0/1 | 0.0/1 | 0.0/0 | all |
| Jock Landale | ATL | 18.1/18 | 6.5/8 | 4.0/6 | 1.0/4 | 0.0/1 | 0.0/1 | all |
| Quenton Jackson | IND | 0.0/17 | 0.0/8 | 0.0/1 | 0.0/3 | 0.0/1 | 0.0/0 | MIN,PTS,REB,AST,STL |
| Morez Johnson Jr. | DAL | 0.0/17 | 0.0/8 | 0.0/6 | 0.0/0 | 0.0/0 | 0.0/0 | MIN,PTS,REB |
| Justin Champagnie | WAS | 20.3/23 | 7.0/8 | 5.0/6 | 1.0/0 | 1.0/1 | 0.0/2 | BLK |
| Collin Murray-Boyles | TOR | 21.2/18 | 8.0/8 | 5.0/3 | 2.0/0 | 1.0/3 | 0.0/0 | all |
| Andrew Wiggins | MIA | 28.5/26 | 11.0/8 | 3.0/8 | 2.0/2 | 1.0/1 | 0.0/0 | REB |
| Tim Hardaway Jr. | MIA | 18.8/21 | 6.0/8 | 1.0/4 | 0.0/1 | 0.0/0 | 0.0/0 | REB |
| Ronald Holland II | DET | 0.0/22 | 0.0/8 | 0.0/5 | 0.0/4 | 0.0/1 | 0.0/0 | MIN,PTS,REB,AST,STL |
| Zach Edey | MEM | 21.3/22 | 10.0/8 | 11.0/10 | 1.0/3 | 0.0/1 | 1.0/2 | AST |
| Scotty Pippen Jr. | MEM | 19.0/17 | 9.0/8 | 2.0/6 | 4.0/3 | 1.0/0 | 0.0/1 | REB |
| Donovan Clingan | POR | 19.2/21 | 8.0/8 | 9.0/11 | 2.0/3 | 0.0/0 | 1.0/3 | BLK |
| Luke Kornet | SAS | 0.0/16 | 0.0/7 | 0.0/3 | 0.0/0 | 0.0/0 | 0.0/1 | MIN,PTS,REB,BLK |
| Jabari Smith Jr. | HOU | 34.4/34 | 12.0/7 | 6.0/5 | 1.0/1 | 0.0/2 | 0.0/2 | all |
| Colin Castleton | ORL | 0.0/4 | 0.0/7 | 0.0/2 | 0.0/1 | 0.0/0 | 0.0/0 | MIN,PTS,AST |
| Alex Sarr | WAS | 0.0/25 | 0.0/7 | 0.0/4 | 0.0/5 | 0.0/2 | 0.0/0 | MIN,PTS,REB,AST,STL |
| Ja'Kobe Walter | TOR | 26.0/24 | 8.0/7 | 2.0/4 | 2.0/2 | 1.0/2 | 0.0/1 | all |
| Pelle Larsson | MIA | 24.1/29 | 7.0/7 | 1.0/2 | 2.0/1 | 1.0/1 | 0.0/0 | all |
| Kasparas Jakučionis | MIL | 0.0/23 | 0.0/7 | 0.0/2 | 0.0/5 | 0.0/2 | 0.0/0 | MIN,PTS,REB,AST,STL |
| Matas Buzelis | CHI | 22.8/17 | 10.0/7 | 4.0/5 | 1.0/3 | 0.0/0 | 0.0/1 | all |
| Jeremiah Fears | NOP | 27.2/24 | 11.0/7 | 2.0/0 | 3.0/1 | 1.0/1 | 0.0/0 | all |
| Karlo Matković | NOP | 0.0/9 | 0.0/7 | 0.0/4 | 0.0/1 | 0.0/2 | 0.0/0 | MIN,PTS,REB,AST,STL |
| Gary Payton II | GSW | 0.0/11 | 0.0/7 | 0.0/2 | 0.0/0 | 0.0/0 | 0.0/0 | MIN,PTS,REB |
| Sandro Mamukelashvili | LAL | 15.1/24 | 6.0/7 | 3.0/5 | 1.0/2 | 0.0/0 | 0.0/0 | MIN |
| Kris Dunn | LAC | 24.1/34 | 6.0/7 | 3.0/4 | 4.0/5 | 2.0/2 | 0.0/0 | MIN |
| Sam Hauser | BOS | 19.5/23 | 6.0/6 | 2.0/2 | 1.0/2 | 0.0/0 | 0.0/0 | all |
| Julian Champagnie | SAS | 27.2/25 | 8.0/6 | 3.0/0 | 1.0/0 | 1.0/3 | 0.0/0 | REB,STL |
| Brandon Miller | CHA | 28.3/23 | 16.0/6 | 4.0/2 | 3.0/0 | 1.0/2 | 0.0/1 | MIN |
| Royce O'Neale | CHA | 17.7/17 | 5.0/6 | 2.0/2 | 1.0/0 | 0.0/1 | 0.0/0 | all |
| Ryan Kalkbrenner | CHA | 15.0/19 | 6.0/6 | 4.0/7 | 1.0/1 | 0.0/0 | 0.0/2 | all |
| Hannes Steinbach | CHA | 0.0/12 | 0.0/6 | 0.0/5 | 0.0/0 | 0.0/0 | 0.0/0 | MIN,PTS,REB |
| Marcus Sasser | DAL | 16.1/27 | 5.0/6 | 0.0/2 | 1.0/3 | 0.0/0 | 0.0/1 | MIN |
| Jase Richardson | ORL | 0.0/14 | 0.0/6 | 0.0/1 | 0.0/3 | 0.0/0 | 0.0/0 | MIN,PTS,REB,AST |
| Khris Middleton | WAS | 0.0/16 | 0.0/6 | 0.0/2 | 0.0/0 | 0.0/2 | 0.0/0 | MIN,PTS,REB,STL |
| Jakob Poeltl | TOR | 18.8/27 | 10.0/6 | 8.0/9 | 2.0/2 | 1.0/1 | 0.0/1 | MIN |
| Klay Thompson | MIA | 16.4/24 | 8.0/6 | 1.0/2 | 1.0/2 | 0.0/0 | 0.0/0 | MIN |
| Josh Giddey | CHI | 24.2/25 | 11.0/6 | 7.0/4 | 6.0/9 | 1.0/0 | 0.0/0 | all |
| Ace Bailey | UTA | 25.4/22 | 8.0/6 | 2.0/7 | 2.0/2 | 0.0/0 | 0.0/0 | REB |
| Yves Missi | NOP | 24.2/9 | 7.0/6 | 6.5/1 | 2.0/0 | 0.0/0 | 1.0/1 | MIN |
| Jerami Grant | MEM | 19.5/26 | 9.0/6 | 1.0/0 | 1.0/3 | 0.0/2 | 0.0/1 | MIN |
| Gradey Dick | LAC | 0.0/12 | 0.0/6 | 0.0/4 | 0.0/0 | 0.0/1 | 0.0/0 | MIN,PTS,REB,STL |
| Isaiah Jackson | LAC | 0.0/28 | 0.0/6 | 0.0/6 | 0.0/3 | 0.0/3 | 0.0/1 | MIN,PTS,REB,AST,STL,BLK |
| Jordan Walsh | BOS | 12.5/20 | 2.0/5 | 3.0/3 | 0.0/0 | 0.0/0 | 0.0/0 | MIN |
| Marcus Smart | HOU | 27.8/21 | 9.0/5 | 1.0/3 | 2.0/1 | 1.0/1 | 0.0/0 | MIN |
| Moussa Diabaté | CHA | 24.7/21 | 7.0/5 | 7.0/8 | 2.0/1 | 1.0/1 | 0.0/1 | all |
| Kingston Flemings | ATL | 13.6/25 | 0.0/5 | 1.0/6 | 1.0/8 | 0.0/1 | 0.0/0 | MIN,PTS,REB,AST |
| Desmond Bane | ORL | 31.3/27 | 14.0/5 | 3.0/2 | 3.0/0 | 1.0/1 | 0.0/0 | MIN,AST |
| Tristan da Silva | ORL | 18.0/29 | 6.0/5 | 2.0/3 | 1.0/1 | 0.0/1 | 0.0/0 | MIN |
| Jamal Shead | TOR | 22.6/24 | 6.0/5 | 1.0/2 | 6.0/5 | 1.0/0 | 0.0/0 | all |
| Jamison Battle | TOR | 18.5/12 | 6.0/5 | 3.0/0 | 1.0/0 | 0.0/1 | 0.0/0 | MIN |
| Nikola Jović | MIA | 20.9/13 | 7.0/5 | 3.0/4 | 2.0/1 | 0.0/1 | 0.0/1 | MIN |
| Kevin Huerter | DET | 8.8/20 | 2.0/5 | 1.0/6 | 0.0/2 | 0.0/1 | 0.0/1 | MIN,REB |
| Javonte Green | DET | 8.6/13 | 2.0/5 | 1.0/3 | 0.0/0 | 0.0/0 | 0.0/1 | all |
| Draymond Green | GSW | 24.9/31 | 7.0/5 | 6.0/5 | 6.0/6 | 1.0/0 | 0.0/1 | all |
| Gui Santos | GSW | 24.5/20 | 7.0/5 | 4.0/4 | 2.0/2 | 1.0/1 | 0.0/1 | all |
| Collin Sexton | LAL | 27.4/16 | 14.0/5 | 1.0/1 | 3.0/2 | 1.0/3 | 0.0/0 | MIN,STL |
| Kobe Sanders | LAC | 0.0/19 | 0.0/5 | 0.0/3 | 0.0/5 | 0.0/1 | 0.0/0 | MIN,PTS,REB,AST,STL |
| Emanuel Sharp | SAC | 0.0/14 | 0.0/5 | 0.0/0 | 0.0/1 | 0.0/0 | 0.0/0 | MIN,PTS,AST |
| Payton Pritchard | BOS | 28.1/30 | 11.0/4 | 2.0/1 | 3.0/4 | 0.0/0 | 0.0/0 | all |
| Mitchell Robinson | BOS | 14.6/22 | 4.0/4 | 6.0/4 | 0.0/2 | 1.0/0 | 0.0/1 | MIN,AST |
| Steven Adams | HOU | 0.0/9 | 0.0/4 | 0.0/2 | 0.0/1 | 0.0/0 | 0.0/0 | MIN,PTS,AST |
| Dennis Schröder | CHA | 18.9/20 | 7.0/4 | 1.0/4 | 2.0/3 | 0.0/0 | 0.0/1 | REB |
| Liam McNeeley | CHA | 0.0/12 | 0.0/4 | 0.0/4 | 0.0/0 | 0.0/0 | 0.0/0 | MIN,PTS,REB |
| Jalen Slawson | IND | 21.7/16 | 6.0/4 | 3.0/5 | 1.0/2 | 1.0/2 | 0.0/2 | all |
| Daniel Gafford | DAL | 19.2/15 | 8.0/4 | 5.0/3 | 1.0/5 | 0.0/0 | 0.0/2 | AST |
| Goga Bitadze | ORL | 12.4/12 | 4.0/4 | 5.0/3 | 1.0/0 | 0.0/0 | 0.0/1 | all |
| Deandre Ayton | WAS | 0.0/14 | 0.0/4 | 0.0/6 | 0.0/1 | 0.0/0 | 0.0/0 | MIN,PTS,REB,AST |
| Bam Adebayo | MIA | 26.2/23 | 13.0/4 | 7.0/6 | 3.0/3 | 1.0/2 | 0.0/0 | all |
| Ausar Thompson | DET | 26.3/19 | 9.0/4 | 5.0/3 | 3.0/5 | 2.0/1 | 0.0/1 | MIN |
| Jalen Duren | DET | 24.1/10 | 13.0/4 | 10.0/6 | 2.0/3 | 0.0/1 | 0.0/1 | MIN |
| Noa Essengue | CHI | 0.0/17 | 0.0/4 | 0.0/1 | 0.0/1 | 0.0/3 | 0.0/1 | MIN,PTS,AST,STL,BLK |
| Bennedict Mathurin | NOP | 18.9/15 | 9.0/4 | 2.0/2 | 1.0/0 | 0.0/0 | 0.0/0 | all |
| Brandon Williams | GSW | 19.4/9 | 8.0/4 | 1.0/2 | 2.0/1 | 1.0/1 | 0.0/0 | all |
| Georges Niang | GSW | 0.0/13 | 0.0/4 | 0.0/3 | 0.0/0 | 0.0/1 | 0.0/0 | MIN,PTS,REB,STL |
| Isaiah Stewart | MEM | 0.0/16 | 0.0/4 | 0.0/2 | 0.0/0 | 0.0/1 | 0.0/0 | MIN,PTS,REB,STL |
| De'Andre Hunter | SAC | 0.0/25 | 0.0/4 | 0.0/7 | 0.0/1 | 0.0/0 | 0.0/0 | MIN,PTS,REB,AST |
| Scoot Henderson | POR | 20.3/21 | 9.0/4 | 1.0/1 | 3.0/2 | 1.0/0 | 0.0/0 | all |
| Bogdan Bogdanović | HOU | 0.0/9 | 0.0/3 | 0.0/1 | 0.0/0 | 0.0/0 | 0.0/0 | MIN,PTS,REB |
| Sion James | CHA | 18.9/24 | 4.0/3 | 2.0/2 | 2.0/5 | 0.0/0 | 0.0/0 | MIN |
| Asa Newell | ATL | 0.0/8 | 0.0/3 | 0.0/1 | 0.0/0 | 0.0/0 | 0.0/0 | MIN,PTS |
| Dorian Finney-Smith | ATL | 0.0/8 | 0.0/3 | 0.0/2 | 0.0/1 | 0.0/0 | 0.0/0 | MIN,PTS,REB,AST |
| Zuby Ejiofor | ATL | 0.0/8 | 0.0/3 | 0.0/2 | 0.0/0 | 0.0/0 | 0.0/0 | MIN,PTS,REB |
| Kelly Oubre Jr. | IND | 25.9/20 | 10.0/3 | 3.0/2 | 1.0/2 | 1.0/1 | 0.0/0 | all |
| Bones Hyland | MIN | 0.0/8 | 0.0/3 | 0.0/1 | 0.0/0 | 0.0/0 | 0.0/0 | MIN,PTS,REB |
| Bub Carrington | WAS | 23.6/11 | 8.0/3 | 2.0/1 | 4.0/0 | 0.0/0 | 0.0/0 | MIN,AST |
| Nick Richards | MIA | 10.8/3 | 4.0/3 | 4.0/0 | 0.0/1 | 0.0/0 | 0.0/0 | all |
| Dru Smith | MIA | 0.0/6 | 0.0/3 | 0.0/0 | 0.0/1 | 0.0/0 | 0.0/0 | MIN,PTS |
| Ousmane Dieng | MIL | 26.0/16 | 8.0/3 | 3.0/1 | 2.0/1 | 1.0/0 | 0.0/0 | MIN |
| Brayden Burries | MIL | 0.0/8 | 0.0/3 | 0.0/1 | 0.0/3 | 0.0/1 | 0.0/0 | MIN,PTS,AST,STL |
| Svi Mykhailiuk | UTA | 16.8/21 | 5.0/3 | 1.0/4 | 1.0/1 | 0.0/1 | 0.0/0 | REB |
| Herbert Jones | NOP | 18.7/18 | 6.0/3 | 1.0/1 | 2.0/0 | 1.0/0 | 0.0/0 | all |
| Al Horford | GSW | 0.0/19 | 0.0/3 | 0.0/5 | 0.0/0 | 0.0/0 | 0.0/2 | MIN,PTS,REB,BLK |
| Daeqwon Plowden | SAC | 20.5/20 | 8.0/3 | 1.0/0 | 1.0/0 | 0.0/0 | 0.0/1 | all |
| Baylor Scheierman | BOS | 16.4/11 | 4.0/2 | 2.0/0 | 1.0/0 | 0.0/0 | 0.0/0 | all |
| Andre Drummond | NYK | 11.8/7 | 3.0/2 | 5.0/2 | 0.0/0 | 0.0/0 | 0.0/0 | all |
| Jose Alvarado | NYK | 14.0/11 | 5.0/2 | 1.0/2 | 2.0/2 | 1.0/1 | 0.0/0 | all |
| Christian Anderson | CHA | 0.0/16 | 0.0/2 | 0.0/0 | 0.0/2 | 0.0/0 | 0.0/1 | MIN,PTS,AST,BLK |
| Jarace Walker | IND | 20.3/17 | 7.0/2 | 3.0/1 | 2.0/1 | 1.0/0 | 0.0/0 | all |
| Allen Graves | TOR | 0.0/6 | 0.0/2 | 0.0/2 | 0.0/0 | 0.0/0 | 0.0/1 | MIN,PTS,BLK |
| Ryan Conwell | MIA | 0.0/3 | 0.0/2 | 0.0/0 | 0.0/0 | 0.0/0 | 0.0/0 | PTS |
| GG Jackson | MEM | 19.0/15 | 9.0/2 | 3.0/4 | 1.0/1 | 0.0/0 | 0.0/0 | all |
| Quinten Post | MEM | 0.0/20 | 0.0/2 | 0.0/1 | 0.0/1 | 0.0/0 | 0.0/2 | MIN,PTS,AST,BLK |
| Hugo González | BOS | 0.0/4 | 0.0/0 | 0.0/0 | 0.0/1 | 0.0/0 | 0.0/0 | MIN,AST |
| Mikal Bridges | NYK | 31.6/22 | 9.0/0 | 2.0/1 | 3.0/4 | 1.0/1 | 0.0/0 | MIN,PTS |
| James Wiseman | NYK | 14.0/2 | 4.0/0 | 3.0/0 | 0.0/0 | 0.0/0 | 0.0/0 | MIN |
| Jordan Clarkson | NYK | 8.1/3 | 3.0/0 | 0.0/1 | 0.0/0 | 0.0/0 | 0.0/0 | all |
| Harrison Barnes | SAS | 19.6/5 | 8.0/0 | 2.0/0 | 1.0/0 | 0.0/0 | 0.0/0 | MIN |
| Carter Bryant | SAS | 0.0/4 | 0.0/0 | 0.0/0 | 0.0/0 | 0.0/0 | 0.0/0 | MIN |
| PJ Hall | CHA | 13.3/10 | 6.0/0 | 5.0/1 | 0.0/3 | 0.0/0 | 0.0/1 | AST |
| Kobe Brown | IND | 25.1/1 | 6.0/0 | 3.0/0 | 1.0/0 | 0.0/0 | 0.0/0 | MIN |
| Jay Huff | IND | 20.2/5 | 8.0/0 | 2.0/2 | 1.0/0 | 0.0/0 | 0.0/0 | all |
| Larry Nance Jr. | IND | 0.0/1 | 0.0/0 | 0.0/0 | 0.0/0 | 0.0/0 | 0.0/0 | all |
| Jamal Cain | ORL | 19.8/11 | 7.0/0 | 3.0/1 | 1.0/0 | 0.0/0 | 0.0/0 | MIN |
| Nikola Vučević | ORL | 9.8/4 | 4.0/0 | 3.0/2 | 0.0/0 | 0.0/0 | 0.0/0 | all |
| Alex Morales | ORL | 0.0/4 | 0.0/0 | 0.0/1 | 0.0/0 | 0.0/0 | 0.0/0 | MIN |
| Jevon Carter | ORL | 0.0/13 | 0.0/0 | 0.0/1 | 0.0/1 | 0.0/2 | 0.0/0 | MIN,REB,AST,STL |
| Cody Williams | MIN | 20.2/3 | 4.0/0 | 1.0/0 | 1.0/0 | 0.0/0 | 0.0/0 | MIN |
| Isaiah Evans | MIN | 0.0/2 | 0.0/0 | 0.0/0 | 0.0/1 | 0.0/0 | 0.0/0 | AST |
| Jaylen Clark | MIN | 0.0/3 | 0.0/0 | 0.0/2 | 0.0/1 | 0.0/0 | 0.0/0 | MIN,REB,AST |
| Myron Gardner | MIA | 0.0/3 | 0.0/0 | 0.0/0 | 0.0/0 | 0.0/0 | 0.0/1 | BLK |
| Simone Fontecchio | MIA | 0.0/3 | 0.0/0 | 0.0/1 | 0.0/0 | 0.0/0 | 0.0/0 | all |
| Tolu Smith | DET | 0.0/2 | 0.0/0 | 0.0/1 | 0.0/0 | 0.0/0 | 0.0/0 | all |
| Kyle Filipowski | UTA | 19.6/8 | 7.0/0 | 5.0/1 | 2.0/0 | 1.0/1 | 0.0/0 | MIN |
| Will Richard | GSW | 0.0/3 | 0.0/0 | 0.0/0 | 0.0/0 | 0.0/1 | 0.0/0 | MIN,STL |
| Kris Murray | MEM | 0.0/13 | 0.0/0 | 0.0/3 | 0.0/1 | 0.0/0 | 0.0/1 | MIN,REB,AST,BLK |
| Kevon Looney | LAL | 16.7/5 | 2.0/0 | 5.0/1 | 1.0/0 | 0.0/0 | 0.0/0 | all |
| Nique Clifford | SAC | 25.9/2 | 7.0/0 | 2.0/0 | 2.0/0 | 1.0/0 | 0.0/0 | MIN |
| Malik Monk | SAC | 0.0/12 | 0.0/0 | 0.0/1 | 0.0/2 | 0.0/0 | 0.0/0 | MIN,REB,AST |
| Vít Krejčí | POR | 0.0/3 | 0.0/0 | 0.0/2 | 0.0/0 | 0.0/0 | 0.0/0 | MIN,REB |

## 2026-10-24

| Metric | Value |
| --- | ---: |
| Games graded | 8 |
| Winner accuracy | 75.0% |
| Spread MAE | 6.75 |
| Total MAE | 24.31 |
| MIN MAE | 6.82 |
| PTS MAE | 5.87 |
| REB MAE | 2.23 |
| AST MAE | 1.52 |
| 10–90 coverage | 82.2% |
| Top picks hit rate | 53.3% (16/30) |
| Top picks avg claimed confidence | 46.3% |

### Games

| Matchup | Pred winner | Actual | Hit | Pred score | Actual score | Pred margin | Act margin | Pred total | Act total |
| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: |
| MIA@CHA | MIA (62%) | CHA | N | MIA 110 – CHA 106 | MIA 110 – CHA 115 | -5.0 | +5.0 | 218.0 | 225.0 |
| BKN@CLE | CLE (88%) | CLE | Y | BKN 101 – CLE 125 | BKN 121 – CLE 125 | +23.0 | +4.0 | 229.0 | 246.0 |
| MIL@PHI | PHI (68%) | PHI | Y | MIL 110 – PHI 120 | MIL 116 – PHI 127 | +10.0 | +11.0 | 230.0 | 243.0 |
| HOU@ATL | HOU (74%) | HOU | Y | HOU 114 – ATL 100 | HOU 121 – ATL 114 | -14.0 | -7.0 | 215.5 | 235.0 |
| WAS@CHI | CHI (55%) | WAS | N | WAS 111 – CHI 116 | WAS 124 – CHI 120 | +6.0 | -4.0 | 227.0 | 244.0 |
| SAS@DAL | SAS (68%) | SAS | Y | SAS 112 – DAL 97 | SAS 122 – DAL 106 | -13.0 | -16.0 | 207.0 | 228.0 |
| NOP@DEN | DEN (62%) | DEN | Y | NOP 104 – DEN 111 | NOP 135 – DEN 141 | +7.0 | +6.0 | 213.0 | 276.0 |
| GSW@PHX | PHX (57%) | PHX | Y | GSW 104 – PHX 110 | GSW 122 – PHX 131 | +6.0 | +9.0 | 216.0 | 253.0 |

### Top confident picks

| Player | Matchup | Stat | Range | Actual | Hit |
| --- | --- | --- | --- | ---: | --- |
| player:202331 | PHI vs MIL | REB | 3-7 | 0 | N |
| player:1631170 | MIL vs PHI | REB | 3-7 | 8 | N |
| player:1630178 | PHI vs MIL | AST | 4-8 | 4 | Y |
| player:203954 | PHI vs MIL | REB | 6-10 | 11 | N |
| player:1642845 | PHI vs MIL | PTS | 7-13 | 17 | N |
| player:1631157 | MIL vs PHI | PTS | 7-13 | 15 | N |
| player:1631170 | MIL vs PHI | PTS | 8-14 | 21 | N |
| player:1630558 | MIA vs CHA | AST | 3-7 | 10 | N |
| player:1629675 | CHA vs MIA | REB | 4-8 | 9 | N |
| player:1631217 | CHA vs MIA | REB | 5-9 | 5 | Y |
| player:203507 | MIA vs CHA | REB | 6-10 | 6 | Y |
| player:1629675 | CHA vs MIA | PTS | 9-15 | 23 | N |
| player:1641706 | CHA vs MIA | PTS | 13-19 | 34 | N |
| player:203507 | MIA vs CHA | PTS | 14-20 | 14 | Y |
| player:1631095 | HOU vs ATL | REB | 4-8 | 5 | Y |
| player:1630596 | CLE vs BKN | AST | 2-6 | 4 | Y |
| player:201142 | HOU vs ATL | AST | 2-6 | 2 | Y |
| player:202331 | PHI vs MIL | STL | 1-3 | 0 | N |
| player:1630230 | DAL vs SAS | AST | 2-6 | 5 | Y |
| player:1631157 | MIL vs PHI | AST | 2-6 | 4 | Y |
| player:1628368 | SAS vs DAL | AST | 2-6 | 9 | N |
| player:201935 | CLE vs BKN | REB | 3-7 | 8 | N |
| player:1627749 | NOP vs DEN | AST | 2-6 | 6 | Y |
| player:1641708 | HOU vs ATL | AST | 3-7 | 6 | Y |
| player:1628970 | PHX vs GSW | REB | 4-8 | 7 | Y |
| player:1626164 | PHX vs GSW | AST | 4-8 | 7 | Y |
| player:1628415 | PHX vs GSW | PTS | 10-16 | 15 | Y |
| player:1626164 | PHX vs GSW | PTS | 17-23 | 43 | N |
| player:1628970 | PHX vs GSW | PTS | 10-16 | 16 | Y |
| player:1630224 | PHX vs GSW | PTS | 12-18 | 12 | Y |

### Player grades (MIN / PTS / REB / AST / STL / BLK)

| Player | Team | MIN pred/act | PTS | REB | AST | STL | BLK | in 10–90 (any miss listed) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Devin Booker | PHX | 34.3/36 | 20.0/43 | 3.0/7 | 6.0/7 | 1.0/0 | 0.0/1 | PTS,REB |
| Jamal Murray | DEN | 35.0/43 | 16.0/42 | 2.0/3 | 6.0/6 | 1.0/1 | 0.0/1 | MIN,PTS |
| Nikola Jokić | DEN | 34.5/44 | 15.0/35 | 8.0/15 | 7.0/10 | 1.0/2 | 0.0/3 | MIN,PTS,BLK |
| Brandon Miller | CHA | 30.2/36 | 15.0/34 | 3.0/8 | 2.0/4 | 1.0/0 | 0.0/1 | MIN,PTS,REB |
| Caleb Wilson | CHI | 28.4/38 | 12.0/30 | 3.0/14 | 0.0/3 | 1.0/2 | 0.0/1 | MIN,PTS,REB,AST |
| Michael Porter Jr. | BKN | 27.8/33 | 15.0/28 | 6.0/9 | 1.0/1 | 0.0/4 | 0.0/0 | STL |
| Joel Embiid | PHI | 28.4/36 | 18.0/28 | 7.0/11 | 3.0/10 | 0.0/1 | 1.0/0 | MIN,AST |
| Tyrese Maxey | PHI | 33.8/36 | 18.0/26 | 2.0/4 | 6.0/4 | 1.0/0 | 0.0/0 | all |
| Jalen Johnson | ATL | 27.6/38 | 12.0/26 | 6.0/9 | 4.0/16 | 1.0/2 | 0.0/0 | MIN,AST |
| Trey Murphy III | NOP | 29.1/37 | 10.0/26 | 2.0/6 | 3.0/4 | 1.0/1 | 0.0/0 | MIN,PTS |
| Yaxel Lendeborg | GSW | 38.7/36 | 11.0/26 | 7.0/9 | 3.0/5 | 1.0/0 | 0.0/1 | PTS |
| Dennis Schröder | CHA | 22.0/38 | 8.0/25 | 1.0/6 | 3.0/4 | 0.0/0 | 0.0/0 | MIN,PTS,REB |
| Trae Young | WAS | 27.2/34 | 12.0/25 | 1.0/4 | 5.0/9 | 1.0/0 | 0.0/0 | MIN,REB |
| De'Anthony Melton | GSW | 31.2/27 | 13.0/25 | 4.0/5 | 3.0/5 | 1.0/3 | 0.0/0 | all |
| Naz Reid | CHA | 30.0/37 | 11.0/23 | 5.0/9 | 2.0/0 | 0.0/0 | 0.0/2 | MIN,BLK |
| Julius Randle | BKN | 28.2/35 | 13.0/23 | 5.0/6 | 2.0/5 | 0.0/0 | 0.0/0 | AST |
| Victor Wembanyama | SAS | 31.6/29 | 17.5/23 | 11.5/7 | 3.0/2 | 1.0/1 | 1.0/4 | all |
| Davion Mitchell | MIA | 30.5/37 | 6.0/22 | 1.0/1 | 5.0/10 | 0.5/1 | 0.0/0 | PTS |
| Donovan Mitchell | CLE | 33.4/35 | 23.0/22 | 4.0/5 | 5.0/4 | 1.0/1 | 0.0/1 | all |
| Egor Dëmin | BKN | 22.4/31 | 6.5/22 | 2.0/4 | 2.0/6 | 0.0/0 | 0.0/0 | MIN,PTS,AST |
| Kevin Durant | HOU | 37.7/37 | 23.0/22 | 4.0/4 | 4.0/2 | 1.0/0 | 1.0/1 | all |
| Kyshawn George | WAS | 20.5/36 | 8.5/22 | 3.0/9 | 3.0/5 | 1.0/0 | 0.0/4 | MIN,PTS,REB,BLK |
| Dylan Harper | SAS | 30.7/28 | 12.0/22 | 3.0/5 | 3.0/2 | 1.0/2 | 0.0/0 | all |
| Dejounte Murray | NOP | 27.0/35 | 11.0/22 | 3.0/6 | 4.0/6 | 1.0/2 | 0.0/1 | MIN |
| Jarrett Allen | CLE | 28.2/27 | 12.0/21 | 9.0/8 | 2.0/0 | 1.0/1 | 0.0/2 | all |
| Jaime Jaquez Jr. | MIL | 28.7/27 | 11.0/21 | 5.0/8 | 2.0/4 | 1.0/0 | 0.0/0 | all |
| Matas Buzelis | CHI | 21.1/35 | 8.0/21 | 4.0/5 | 1.0/2 | 0.0/1 | 0.0/0 | MIN,PTS |
| Sergio de Larrea | DAL | 1.9/33 | 0.0/21 | 0.0/5 | 0.0/4 | 0.0/0 | 0.0/0 | MIN,PTS,AST |
| Grayson Allen | CHA | 22.0/34 | 8.0/20 | 1.0/3 | 1.0/5 | 0.5/1 | 0.0/0 | MIN,AST |
| Bam Adebayo | MIA | 23.0/39 | 12.0/20 | 7.0/8 | 3.0/4 | 1.0/1 | 0.0/1 | MIN |
| Evan Mobley | CLE | 33.2/35 | 15.0/20 | 10.0/10 | 3.0/4 | 1.0/2 | 1.0/3 | BLK |
| Brandon Williams | GSW | 24.3/24 | 10.5/20 | 2.0/3 | 2.0/5 | 1.0/2 | 0.0/0 | all |
| Kel'el Ware | MIL | 0.0/29 | 0.0/19 | 0.0/13 | 0.0/1 | 0.0/1 | 0.0/2 | MIN,PTS,REB,AST,STL,BLK |
| Reed Sheppard | HOU | 19.2/30 | 3.0/19 | 0.0/6 | 1.5/7 | 1.0/2 | 0.0/0 | REB,AST |
| Tari Eason | HOU | 25.1/31 | 9.0/19 | 5.0/3 | 1.0/0 | 1.0/1 | 0.0/1 | all |
| Anthony Davis | WAS | 27.7/31 | 12.5/19 | 8.0/6 | 1.0/4 | 0.0/1 | 1.0/0 | all |
| De'Aaron Fox | SAS | 31.1/28 | 14.0/19 | 2.0/3 | 4.0/9 | 1.0/3 | 0.0/1 | all |
| Stephon Castle | SAS | 28.5/28 | 12.5/19 | 3.0/4 | 5.0/8 | 1.0/3 | 0.0/0 | all |
| Nickeil Alexander-Walker | ATL | 28.0/32 | 10.0/18 | 1.0/5 | 2.0/4 | 1.0/3 | 0.0/0 | REB,STL |
| Dyson Daniels | ATL | 24.1/29 | 7.0/18 | 3.0/8 | 3.0/3 | 2.0/1 | 0.0/0 | PTS |
| Norman Powell | CHI | 23.3/33 | 15.0/18 | 2.0/2 | 1.0/3 | 1.0/4 | 0.0/0 | MIN,STL |
| VJ Edgecombe | PHI | 29.4/30 | 10.0/17 | 3.5/13 | 3.0/2 | 1.0/1 | 0.0/2 | REB,BLK |
| CJ McCollum | ATL | 23.8/30 | 13.0/17 | 2.0/2 | 2.0/1 | 0.0/0 | 0.0/0 | MIN |
| Amen Thompson | HOU | 37.5/39 | 13.0/17 | 7.0/11 | 5.0/6 | 1.0/1 | 1.0/0 | all |
| Alperen Sengun | HOU | 34.6/33 | 18.0/17 | 9.0/10 | 6.0/7 | 1.0/1 | 1.0/0 | all |
| Trevon Brazile | DEN | 17.4/28 | 4.0/17 | 7.0/9 | 0.0/0 | 0.0/1 | 0.0/2 | MIN,PTS,BLK |
| Zion Williamson | NOP | 27.6/33 | 17.0/17 | 4.0/1 | 3.0/2 | 1.0/2 | 0.0/2 | MIN,BLK |
| Derik Queen | NOP | 26.1/25 | 9.0/17 | 6.0/8 | 3.0/2 | 1.0/0 | 0.0/0 | all |
| Aaron Wiggins | ATL | 16.6/28 | 7.0/16 | 1.0/5 | 0.5/2 | 0.0/1 | 0.0/1 | MIN |
| Miles Bridges | PHX | 29.8/33 | 12.5/16 | 6.0/7 | 2.0/3 | 0.0/0 | 0.0/0 | all |
| Pelle Larsson | MIA | 24.2/36 | 6.0/15 | 1.0/7 | 2.0/4 | 0.0/1 | 0.0/0 | MIN,REB |
| Jaylon Tyson | CLE | 15.3/21 | 5.0/15 | 3.0/1 | 2.0/4 | 0.0/1 | 0.0/0 | all |
| Ryan Rollins | MIL | 26.2/25 | 11.0/15 | 3.0/4 | 4.0/4 | 1.0/1 | 0.0/1 | all |
| Christian Braun | DEN | 28.5/40 | 8.0/15 | 3.0/8 | 2.0/2 | 0.0/2 | 0.0/0 | MIN,REB |
| Dillon Brooks | PHX | 32.8/34 | 13.0/15 | 3.0/2 | 1.0/5 | 1.0/0 | 0.0/0 | AST |
| Giannis Antetokounmpo | MIA | 27.2/25 | 18.0/14 | 8.0/6 | 3.0/3 | 0.0/1 | 0.0/0 | all |
| Klay Thompson | MIA | 16.8/27 | 7.0/14 | 1.0/3 | 1.0/0 | 0.0/1 | 0.0/0 | MIN |
| Kyle Kuzma | MIL | 23.0/35 | 10.5/14 | 5.0/12 | 2.0/3 | 0.0/0 | 0.0/0 | MIN,REB |
| Jabari Smith Jr. | HOU | 37.2/33 | 12.0/14 | 5.5/5 | 1.0/3 | 1.0/0 | 0.0/1 | all |
| Jalen Smith | CHI | 17.6/24 | 7.0/14 | 6.0/3 | 1.0/1 | 0.0/0 | 0.0/0 | all |
| Saddiq Bey | NOP | 24.3/25 | 8.0/14 | 3.0/4 | 2.0/3 | 0.0/1 | 0.0/0 | all |
| Bobby Portis Jr. | MIA | 20.2/27 | 7.0/13 | 4.5/8 | 1.0/0 | 0.0/2 | 0.0/0 | MIN |
| Tyler Herro | MIL | 26.1/31 | 14.0/13 | 4.0/6 | 2.0/3 | 0.0/0 | 0.0/0 | all |
| Tre Johnson | WAS | 20.5/23 | 9.0/13 | 1.0/2 | 1.0/2 | 0.0/0 | 0.0/0 | all |
| James Harden | CLE | 33.2/33 | 17.0/12 | 5.0/8 | 6.0/7 | 1.0/0 | 0.0/2 | all |
| Kasparas Jakučionis | MIL | 19.0/25 | 6.0/12 | 2.0/3 | 1.0/2 | 0.0/2 | 0.0/0 | all |
| P.J. Washington | DAL | 39.3/36 | 13.0/12 | 6.0/4 | 2.0/2 | 1.0/0 | 1.0/0 | all |
| Marcus Sasser | DAL | 27.6/27 | 8.0/12 | 1.0/3 | 2.5/5 | 1.0/0 | 0.0/0 | all |
| Daniel Gafford | DAL | 28.9/23 | 10.0/12 | 8.0/9 | 1.0/2 | 1.0/3 | 1.0/2 | STL |
| Julian Champagnie | SAS | 26.2/28 | 8.0/12 | 3.0/5 | 1.0/3 | 1.0/1 | 0.0/3 | BLK |
| DeMar DeRozan | DEN | 22.2/24 | 10.0/12 | 1.0/3 | 2.0/3 | 0.0/0 | 0.0/0 | all |
| Jalen Green | PHX | 31.6/26 | 15.0/12 | 3.0/2 | 3.0/1 | 1.0/1 | 0.0/0 | all |
| Graham Ike | GSW | 16.7/26 | 8.0/12 | 4.0/10 | 1.0/2 | 1.0/1 | 0.0/0 | MIN |
| Peyton Watson | CLE | 21.1/31 | 8.0/11 | 2.0/3 | 1.0/4 | 0.5/1 | 1.0/1 | MIN,AST |
| AJ Green | MIL | 21.7/19 | 6.0/11 | 2.0/3 | 1.0/0 | 0.0/0 | 0.0/0 | all |
| Bogdan Bogdanović | HOU | 10.3/20 | 4.0/11 | 1.0/1 | 1.0/1 | 0.0/0 | 0.0/0 | MIN |
| Justin Champagnie | WAS | 19.6/26 | 5.5/11 | 4.0/14 | 1.0/4 | 1.0/1 | 0.0/0 | MIN,REB,AST |
| Zaccharie Risacher | DAL | 29.6/32 | 11.5/11 | 4.0/4 | 1.0/2 | 1.0/1 | 0.0/2 | all |
| Devin Vassell | SAS | 32.4/32 | 10.0/11 | 2.0/4 | 3.0/6 | 1.0/2 | 0.0/0 | AST |
| Luke Kennard | PHX | 19.5/18 | 3.0/11 | 1.0/4 | 1.0/1 | 0.0/1 | 0.0/0 | all |
| Collin Gillespie | PHX | 25.2/28 | 7.0/11 | 2.0/4 | 4.0/9 | 1.0/2 | 0.0/0 | all |
| Will Richard | GSW | 12.7/31 | 3.0/11 | 1.0/0 | 1.0/1 | 0.0/2 | 0.0/1 | MIN |
| Chaney Johnson | BKN | 0.0/27 | 0.0/10 | 0.0/5 | 0.0/3 | 0.0/2 | 0.0/0 | MIN,PTS,REB,AST,STL |
| Brayden Burries | MIL | 0.0/17 | 0.0/10 | 0.0/5 | 0.0/2 | 0.0/0 | 0.0/0 | MIN,PTS,REB,AST |
| Tre Jones | CHI | 19.5/18 | 6.5/10 | 1.5/2 | 4.0/3 | 1.0/1 | 0.0/0 | all |
| Alex Sarr | WAS | 20.6/23 | 8.0/10 | 5.0/2 | 2.0/3 | 0.0/0 | 0.0/3 | BLK |
| Naji Marshall | DAL | 37.4/21 | 11.0/10 | 3.0/4 | 4.0/5 | 1.0/1 | 0.0/0 | MIN |
| Jeremiah Fears | NOP | 26.8/23 | 10.0/10 | 2.0/6 | 3.0/2 | 1.0/1 | 0.0/0 | REB |
| Charles Bassey | GSW | 11.6/13 | 5.5/10 | 5.0/7 | 0.0/0 | 0.0/0 | 0.0/2 | all |
| Mario Hezonja | CLE | 18.5/20 | 6.0/9 | 2.0/5 | 1.0/1 | 1.0/1 | 0.0/0 | all |
| Josh Giddey | CHI | 23.4/30 | 11.0/9 | 6.0/8 | 5.5/10 | 1.0/1 | 0.0/0 | all |
| Buddy Hield | CHI | 8.0/16 | 3.0/9 | 0.0/2 | 0.0/2 | 0.0/0 | 0.0/0 | MIN |
| Bub Carrington | WAS | 18.9/21 | 7.0/9 | 2.0/2 | 3.0/1 | 0.0/0 | 0.0/0 | all |
| Bennedict Mathurin | NOP | 0.0/20 | 0.0/9 | 0.0/4 | 0.0/4 | 0.0/0 | 0.0/0 | MIN,PTS,REB,AST |
| DeAndre Jordan | NOP | 0.0/20 | 0.0/9 | 0.0/9 | 0.0/2 | 0.0/0 | 0.0/1 | MIN,PTS,REB,AST,BLK |
| Jordan Goodwin | PHX | 19.6/20 | 5.0/9 | 4.0/2 | 2.0/4 | 1.0/3 | 0.0/0 | all |
| Khaman Maluach | PHX | 12.9/28 | 4.0/9 | 5.0/9 | 0.0/3 | 0.0/1 | 0.0/2 | MIN,AST,STL |
| Mikel Brown Jr. | BKN | 0.0/20 | 0.0/8 | 0.0/2 | 0.0/5 | 0.0/2 | 0.0/0 | MIN,PTS,REB,AST,STL |
| Onyeka Okongwu | ATL | 25.9/26 | 9.0/8 | 6.0/6 | 2.0/2 | 1.0/1 | 0.0/1 | all |
| Sam Merrill | CLE | 22.2/21 | 8.0/7 | 2.0/2 | 2.0/3 | 1.0/0 | 0.0/0 | all |
| Day'Ron Sharpe | BKN | 19.1/23 | 7.0/7 | 8.0/8 | 2.0/1 | 1.0/1 | 0.0/0 | all |
| Luguentz Dort | ATL | 19.4/23 | 5.0/7 | 2.0/2 | 0.0/3 | 1.0/1 | 0.0/0 | AST |
| Leonard Miller | CHI | 25.2/21 | 10.0/7 | 7.0/4 | 1.0/0 | 1.0/1 | 0.0/0 | all |
| Bilal Coulibaly | WAS | 22.2/25 | 6.0/7 | 3.0/4 | 2.0/0 | 1.0/2 | 0.0/0 | all |
| Keldon Johnson | SAS | 17.7/26 | 7.0/7 | 3.0/6 | 1.0/3 | 0.0/0 | 0.0/0 | MIN |
| Aaron Gordon | DEN | 27.1/37 | 11.0/7 | 4.0/5 | 2.0/4 | 0.0/2 | 0.0/0 | MIN |
| Gui Santos | GSW | 31.6/23 | 9.0/7 | 5.0/4 | 3.0/3 | 1.0/0 | 0.0/0 | all |
| Ryan Kalkbrenner | CHA | 19.0/23 | 6.0/6 | 4.5/5 | 1.0/2 | 0.0/0 | 0.0/2 | all |
| Keon Ellis | BKN | 0.0/22 | 0.0/6 | 0.0/2 | 0.0/1 | 0.0/2 | 0.0/0 | MIN,PTS,REB,AST,STL |
| Moritz Wagner | BKN | 0.0/14 | 0.0/6 | 0.0/4 | 0.0/1 | 0.0/0 | 0.0/0 | MIN,PTS,REB,AST |
| Jabari Walker | PHI | 0.0/12 | 0.0/6 | 0.0/3 | 0.0/1 | 0.0/1 | 0.0/0 | MIN,PTS,REB,AST,STL |
| Deandre Ayton | WAS | 16.3/16 | 7.0/6 | 7.0/5 | 0.0/0 | 0.0/1 | 0.0/0 | all |
| Morez Johnson Jr. | DAL | 21.5/12 | 10.0/6 | 7.0/1 | 0.0/2 | 0.0/1 | 0.0/0 | all |
| Jordan Poole | NOP | 18.0/22 | 9.0/6 | 1.0/3 | 2.0/7 | 0.0/1 | 0.0/1 | REB,AST |
| Tim Hardaway Jr. | MIA | 18.5/21 | 6.0/5 | 1.0/0 | 0.0/0 | 0.0/1 | 0.0/2 | BLK |
| Tyrese Proctor | CLE | 2.3/11 | 0.0/5 | 0.0/2 | 0.0/3 | 0.0/1 | 0.0/0 | MIN |
| Max Christie | DAL | 24.7/26 | 5.0/5 | 1.0/5 | 1.0/1 | 0.0/1 | 0.0/2 | REB,BLK |
| Jett Howard | DAL | 9.5/4 | 3.0/5 | 1.0/0 | 0.0/0 | 0.0/0 | 0.0/0 | all |
| Tobi Lawal | DAL | 0.3/4 | 0.0/5 | 0.0/1 | 0.0/1 | 0.0/0 | 0.0/0 | PTS |
| Marvin Bagley III | DEN | 15.0/9 | 7.0/5 | 4.0/4 | 0.0/0 | 0.0/0 | 0.0/0 | all |
| Ryan Dunn | PHX | 22.6/13 | 6.0/5 | 5.0/5 | 2.0/0 | 1.0/1 | 0.0/2 | MIN,BLK |
| Moussa Diabaté | CHA | 26.7/22 | 8.0/4 | 7.5/5 | 2.0/2 | 1.0/2 | 0.0/0 | all |
| Andrew Wiggins | MIA | 26.1/18 | 10.5/4 | 3.0/1 | 2.0/1 | 1.0/1 | 0.0/2 | MIN,BLK |
| Noah Clowney | BKN | 18.8/20 | 7.0/4 | 3.0/4 | 1.0/0 | 0.0/0 | 0.0/1 | all |
| Josh Minott | BKN | 18.5/9 | 5.0/4 | 2.0/2 | 0.0/0 | 1.0/0 | 0.0/0 | all |
| Moussa Cissé | DAL | 14.1/7 | 6.0/4 | 6.0/4 | 0.0/0 | 0.0/0 | 0.0/0 | all |
| Carter Bryant | SAS | 6.0/10 | 2.0/4 | 1.0/1 | 0.0/0 | 0.0/0 | 0.0/0 | MIN |
| Cam Whitmore | DEN | 16.2/11 | 6.0/4 | 2.0/2 | 0.0/0 | 0.0/1 | 0.0/0 | all |
| Georges Niang | GSW | 26.2/23 | 8.0/4 | 4.0/4 | 1.0/2 | 0.0/0 | 0.0/0 | all |
| Tidjane Salaün | CHA | 13.5/10 | 5.0/3 | 3.0/3 | 1.0/0 | 0.0/0 | 0.0/0 | all |
| Ryan Conwell | MIA | 0.6/4 | 0.0/3 | 0.0/1 | 0.0/0 | 0.0/0 | 0.0/0 | REB |
| Craig Porter Jr. | CLE | 4.0/5 | 0.0/3 | 0.0/1 | 0.0/1 | 0.0/0 | 0.0/1 | all |
| Nolan Traore | BKN | 19.4/5 | 6.5/3 | 1.0/2 | 3.0/0 | 1.0/0 | 0.0/0 | MIN |
| Walter Clayton Jr. | DAL | 20.5/14 | 5.0/3 | 2.0/2 | 2.0/5 | 0.0/1 | 0.0/0 | all |
| Ja'Kobi Gillespie | SAS | 0.3/3 | 0.0/3 | 0.0/0 | 0.0/0 | 0.0/0 | 0.0/0 | MIN,PTS |
| Karlo Matković | NOP | 0.0/8 | 0.0/3 | 0.0/0 | 0.0/0 | 0.0/0 | 0.0/0 | MIN,PTS |
| LJ Cryer | GSW | 21.7/14 | 9.5/3 | 2.0/1 | 1.0/1 | 0.0/0 | 0.0/0 | all |
| Kingston Flemings | ATL | 19.9/15 | 2.0/2 | 2.0/1 | 2.0/2 | 0.0/0 | 0.0/0 | all |
| Jock Landale | ATL | 18.3/19 | 4.0/2 | 3.5/4 | 1.0/2 | 0.0/0 | 0.0/0 | all |
| Clint Capela | HOU | 0.3/11 | 0.0/2 | 0.0/3 | 0.0/1 | 0.0/0 | 0.0/0 | MIN,PTS |
| Zach Collins | CHI | 13.9/11 | 5.5/2 | 4.0/3 | 1.0/1 | 0.0/0 | 0.0/0 | all |
| Will Riley | WAS | 18.5/5 | 5.0/2 | 2.0/0 | 1.0/0 | 0.0/0 | 0.0/0 | MIN |
| Tarris Reed Jr. | SAS | 0.2/7 | 0.0/2 | 0.0/3 | 0.0/0 | 0.0/0 | 0.0/0 | MIN |
| Tyus Jones | DEN | 8.4/10 | 2.0/2 | 0.0/0 | 1.0/0 | 0.0/0 | 0.0/0 | all |
| Bryce Hopkins | DEN | 0.5/19 | 0.0/2 | 0.0/2 | 0.0/1 | 0.0/0 | 0.0/0 | MIN |
| Herbert Jones | NOP | 19.1/16 | 5.0/2 | 1.0/3 | 2.0/1 | 1.0/1 | 0.0/0 | all |
| Gary Payton II | GSW | 24.3/17 | 8.0/2 | 4.0/1 | 2.0/0 | 1.0/0 | 0.0/0 | MIN |
| Malevy Leons | GSW | 16.7/4 | 3.0/2 | 3.0/0 | 1.0/0 | 0.0/1 | 0.0/0 | all |
| Nate Ament | MIL | 0.0/11 | 0.0/1 | 0.0/3 | 0.0/0 | 0.0/1 | 0.0/0 | MIN,PTS,REB,STL |
| Sion James | CHA | 23.9/26 | 5.0/0 | 2.5/5 | 3.0/5 | 1.0/0 | 0.0/0 | all |
| Royce O'Neale | CHA | 20.7/11 | 5.0/0 | 2.0/1 | 1.0/0 | 0.0/0 | 0.0/0 | all |
| Christian Anderson | CHA | 15.8/3 | 3.0/0 | 1.0/1 | 2.0/0 | 2.0/0 | 0.0/0 | MIN |
| Nikola Jović | MIA | 19.7/6 | 6.0/0 | 3.0/2 | 2.0/0 | 0.0/0 | 0.0/0 | MIN |
| Adem Bona | PHI | 19.7/10 | 6.0/0 | 4.0/1 | 0.0/1 | 0.0/1 | 1.0/0 | MIN |
| Myles Turner | MIL | 25.4/20 | 11.0/0 | 6.0/5 | 1.0/1 | 0.0/0 | 1.0/1 | PTS |
| Bruce Thornton | HOU | 0.3/4 | 0.0/0 | 0.0/0 | 0.0/0 | 0.0/1 | 0.0/0 | MIN,STL |
| Isaac Okoro | CHI | 21.4/14 | 6.0/0 | 1.0/1 | 1.0/0 | 1.0/0 | 0.0/0 | MIN |
| Harrison Barnes | SAS | 19.8/4 | 8.0/0 | 2.0/0 | 1.0/0 | 0.0/0 | 0.0/0 | MIN |
| Luke Kornet | SAS | 12.1/14 | 4.0/0 | 3.0/4 | 1.0/1 | 0.0/0 | 0.0/0 | all |
| Jordan McLaughlin | SAS | 0.6/3 | 0.0/0 | 0.0/1 | 0.0/0 | 0.0/0 | 0.0/0 | all |
| Duop Reath | PHX | 9.3/3 | 3.0/0 | 1.0/0 | 0.0/0 | 0.0/0 | 0.0/0 | all |
