"""Self-contained typical-game replay page. Presentation only."""

from __future__ import annotations

import json

from sim.possession_log import PossessionEvent, PossessionLog

_ZONE_LABEL = {
    "restricted_area": "layup",
    "paint_non_ra": "paint shot",
    "midrange": "midrange",
    "left_corner_3": "corner 3",
    "right_corner_3": "corner 3",
    "above_break_3": "pull-up 3",
}


def describe_play(event: PossessionEvent) -> str:
    """Broadcast caption for one possession."""
    zone = _ZONE_LABEL.get(event.shot_zone or "", "shot")
    if event.outcome in {"make_2", "make_3"} and event.shot_made:
        who = event.shooter_name or "Shot"
        text = f"{who} {zone} - MADE"
        if event.passer_name:
            text += f" (assist {event.passer_name})"
        if event.fta:
            text += f", free throw {event.ftm}-{event.fta}"
        return text
    if event.shot_made is False and event.shooter_name:
        text = f"{event.shooter_name} {zone} - MISS"
        if event.rebound == "off" and event.rebounder_name:
            text += f" ({event.rebounder_name} offensive rebound)"
        elif event.rebound == "def" and event.rebounder_name:
            text += f" ({event.rebounder_name} defensive rebound)"
        elif event.rebound == "off":
            text += " (team offensive rebound)"
        elif event.rebound == "def":
            text += " (team defensive rebound)"
        if event.fta:
            text += f", free throws {event.ftm}-{event.fta}"
        return text
    if event.outcome == "steal":
        stealer = event.stealer_name or "Defense"
        if event.turnover_name:
            return f"{stealer} steal ({event.turnover_name} turnover)"
        return f"{stealer} steal"
    if event.outcome == "turnover":
        who = event.turnover_name or event.shooter_name or "Turnover"
        return f"{who} turnover"
    if event.fta:
        who = event.shooter_name or "Free throws"
        return f"{who} free throws {event.ftm}-{event.fta}"
    return event.outcome.replace("_", " ")


def annotate_captions(log: PossessionLog) -> None:
    for event in log.events:
        event.caption = describe_play(event)


def render_replay_html(log: PossessionLog) -> str:
    annotate_captions(log)
    payload = json.dumps(log.as_dict(), separators=(",", ":")).replace("<", "\\u003c")
    title = f"{log.away_abbr} @ {log.home_abbr}"
    return _PAGE.replace("__GAME_JSON__", payload).replace("__TITLE__", title)


_PAGE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>__TITLE__ typical game</title>
<style>
:root { color-scheme: dark; }
* { box-sizing: border-box; }
body { margin: 0; background: #07090d; color: #f4f7fb; font-family: "Avenir Next Condensed", "Arial Narrow", "Helvetica Neue", Arial, sans-serif; }
.wrap { max-width: 1180px; margin: 0 auto; padding: 16px 18px 28px; }
.kicker { letter-spacing: 0.14em; text-transform: uppercase; color: #93a0b5; font-size: 12px; margin: 0 0 10px; }
.bug { display: grid; grid-template-columns: 1fr auto 1fr; gap: 12px; align-items: center; background: #10151e; border: 1px solid #243044; padding: 12px 16px; }
.team { display: flex; flex-direction: column; gap: 2px; }
.team.right { text-align: right; align-items: flex-end; }
.name { font-size: 22px; letter-spacing: 0.08em; }
.score { font-size: 56px; line-height: 0.9; font-weight: 700; font-variant-numeric: tabular-nums; }
.clockbox { text-align: center; }
.qtr { font-size: 14px; letter-spacing: 0.16em; color: #f5c451; }
.clock { font-size: 32px; font-variant-numeric: tabular-nums; }
.wp { display: flex; justify-content: space-between; margin-top: 8px; color: #c5d0de; font-size: 14px; letter-spacing: 0.06em; }
.stage { display: grid; grid-template-columns: 250px 1fr 250px; gap: 12px; margin-top: 12px; align-items: start; }
.panel { background: #10151e; border: 1px solid #243044; min-height: 280px; }
.panel h2 { margin: 0; padding: 8px 10px; font-size: 13px; letter-spacing: 0.12em; border-bottom: 1px solid #243044; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { padding: 4px 6px; text-align: right; font-variant-numeric: tabular-nums; }
th:first-child, td:first-child { text-align: left; }
th { color: #93a0b5; font-weight: 600; }
tr.hot td { background: #1c2838; }
.courtbox { background: #10151e; border: 1px solid #243044; padding: 8px; }
svg.court { width: 100%; height: auto; background: #0e1520; display: block; }
.caption { min-height: 44px; margin: 8px 0 0; font-size: 20px; letter-spacing: 0.02em; }
.controls { display: flex; gap: 8px; align-items: center; margin-top: 12px; }
button { background: #182232; color: #f4f7fb; border: 1px solid #31445f; padding: 6px 12px; font: inherit; letter-spacing: 0.08em; cursor: pointer; }
button.on { background: #f5c451; color: #17130a; border-color: #f5c451; }
input[type="range"] { flex: 1; accent-color: #f5c451; }
.chart { margin-top: 10px; background: #10151e; border: 1px solid #243044; }
.chart svg { width: 100%; height: 72px; display: block; }
.fit { color: #93a0b5; font-size: 12px; margin-top: 8px; }
@media (max-width: 900px) {
  .stage { grid-template-columns: 1fr; }
  .score { font-size: 42px; }
}
</style></head><body>
<div class="wrap">
<p class="kicker" id="kicker"></p>
<div class="bug">
  <div class="team"><div class="name" id="away-name"></div><div class="score" id="away-score">0</div></div>
  <div class="clockbox"><div class="qtr" id="qtr">Q1</div><div class="clock" id="clock">12:00</div></div>
  <div class="team right"><div class="name" id="home-name"></div><div class="score" id="home-score">0</div></div>
</div>
<div class="wp"><span id="away-wp"></span><span id="home-wp"></span></div>
<div class="stage">
  <div class="panel"><h2 id="away-head"></h2><div id="away-box"></div></div>
  <div class="courtbox">
    <svg class="court" viewBox="0 0 500 470">
      <rect x="20" y="16" width="460" height="430" fill="none" stroke="#d7e0ea" stroke-width="2"/>
      <line x1="20" y1="16" x2="480" y2="16" stroke="#d7e0ea" stroke-width="2"/>
      <rect x="190" y="326" width="120" height="120" fill="none" stroke="#d7e0ea" stroke-width="2"/>
      <circle cx="250" cy="326" r="60" fill="none" stroke="#d7e0ea" stroke-width="2"/>
      <path d="M70 446 L70 400 A180 180 0 0 1 430 400 L430 446" fill="none" stroke="#d7e0ea" stroke-width="2"/>
      <path d="M210 426 A40 40 0 0 1 290 426" fill="none" stroke="#d7e0ea" stroke-width="2"/>
      <circle cx="250" cy="416" r="8" fill="none" stroke="#f5c451" stroke-width="2"/>
      <line x1="230" y1="446" x2="270" y2="446" stroke="#f5c451" stroke-width="3"/>
      <circle id="shot" cx="250" cy="120" r="8" fill="#3dd68c" opacity="0"/>
    </svg>
    <p class="caption" id="caption"></p>
  </div>
  <div class="panel"><h2 id="home-head"></h2><div id="home-box"></div></div>
</div>
<div class="controls">
  <button type="button" id="play">Play</button>
  <button type="button" class="spd on" data-speed="1">1x</button>
  <button type="button" class="spd" data-speed="2">2x</button>
  <button type="button" class="spd" data-speed="4">4x</button>
  <input id="scrub" type="range" min="0" max="0" value="0">
</div>
<div class="chart"><svg id="wpchart" viewBox="0 0 600 72" preserveAspectRatio="none"></svg></div>
<p class="fit" id="fit"></p>
</div>
<script>
const GAME = __GAME_JSON__;
const ZONE = {
  restricted_area: [250, 405],
  paint_non_ra: [250, 360],
  midrange: [250, 270],
  left_corner_3: [55, 428],
  right_corner_3: [445, 428],
  above_break_3: [250, 175]
};
const COLOR = {
  ATL:"#e03a3e", BOS:"#007a33", BKN:"#ffffff", CHA:"#1d1160", CHI:"#ce1141",
  CLE:"#860038", DAL:"#00538c", DEN:"#0e2240", DET:"#c8102e", GSW:"#1d428a",
  HOU:"#ce1141", IND:"#002d62", LAC:"#c8102e", LAL:"#552583", MEM:"#5d76a9",
  MIA:"#98002e", MIL:"#00471b", MIN:"#0c2340", NOP:"#0c2340", NYK:"#f58426",
  OKC:"#007ac1", ORL:"#0077c0", PHI:"#006bb6", PHX:"#1d1160", POR:"#e03a3e",
  SAC:"#5a2d81", SAS:"#c4ced4", TOR:"#ce1141", UTA:"#002b5c", WAS:"#002b5c"
};
const events = GAME.events || [];
const players = GAME.players || [];
const away = GAME.away_abbr;
const home = GAME.home_abbr;
let cursor = 0;
let timer = null;
let stepMs = 160;

function absTime(e) {
  if (!e) return 0;
  if (e.period <= 4) {
    const qClock = e.clock_remaining - (4 - e.period) * 720;
    return (e.period - 1) * 720 + (720 - qClock);
  }
  return 2880 + (e.period - 5) * 300 + (300 - e.clock_remaining);
}
function clockText(e) {
  if (!e) return "12:00";
  if (e.game_clock) return e.game_clock;
  let remain = e.period <= 4
    ? e.clock_remaining - (4 - e.period) * 720
    : e.clock_remaining;
  remain = Math.max(0, Math.round(remain));
  const m = Math.floor(remain / 60);
  const s = remain % 60;
  return m + ":" + String(s).padStart(2, "0");
}
function qLabel(period) {
  if (!period || period <= 4) return "Q" + (period || 1);
  return period === 5 ? "OT" : "OT" + (period - 4);
}
function box(team, lines, hotId) {
  const head = "<table><tr><th>Player</th><th>MIN</th><th>PTS</th><th>REB</th><th>AST</th></tr>";
  const body = lines.filter(p => p.team === team).map(p => {
    const hot = p.player_id === hotId ? " class=\\"hot\\"" : "";
    return "<tr" + hot + "><td>" + p.name + "</td><td>" + p.min.toFixed(1)
      + "</td><td>" + p.pts + "</td><td>" + p.reb + "</td><td>" + p.ast + "</td></tr>";
  }).join("");
  return head + body + "</table>";
}
function render(index) {
  const e = index >= 0 ? events[index] : null;
  const end = events.length ? absTime(events[events.length - 1]) : 2880;
  const frac = e ? Math.min(1, absTime(e) / (end || 1)) : 0;
  const tally = {};
  players.forEach(p => { tally[p.player_id] = {pts:0, reb:0, ast:0}; });
  for (let i = 0; i <= index && i < events.length; i++) {
    const ev = events[i];
    if (ev.shooter_id != null && ev.points) {
      if (!tally[ev.shooter_id]) tally[ev.shooter_id] = {pts:0, reb:0, ast:0};
      tally[ev.shooter_id].pts += ev.points;
    }
    if (ev.rebounder_id != null) {
      if (!tally[ev.rebounder_id]) tally[ev.rebounder_id] = {pts:0, reb:0, ast:0};
      tally[ev.rebounder_id].reb += 1;
    }
    if (ev.passer_id != null && ev.shot_made) {
      if (!tally[ev.passer_id]) tally[ev.passer_id] = {pts:0, reb:0, ast:0};
      tally[ev.passer_id].ast += 1;
    }
  }
  const lines = players.map(p => {
    const t = tally[p.player_id] || {pts:0, reb:0, ast:0};
    return {player_id:p.player_id, name:p.name, team:p.team, min:p.min * frac, pts:t.pts, reb:t.reb, ast:t.ast};
  });
  const homeWp = e && e.home_win_prob != null ? e.home_win_prob : 0.5;
  document.getElementById("away-score").textContent = e ? e.away_pts : 0;
  document.getElementById("home-score").textContent = e ? e.home_pts : 0;
  document.getElementById("qtr").textContent = qLabel(e ? e.period : 1);
  document.getElementById("clock").textContent = clockText(e);
  document.getElementById("away-wp").textContent = away + " WIN " + Math.round((1 - homeWp) * 100) + "%";
  document.getElementById("home-wp").textContent = home + " WIN " + Math.round(homeWp * 100) + "%";
  document.getElementById("caption").textContent = e ? (e.caption || "") : "Tip";
  const hot = e ? (e.shooter_id || e.rebounder_id || e.stealer_id) : null;
  document.getElementById("away-box").innerHTML = box(away, lines, hot);
  document.getElementById("home-box").innerHTML = box(home, lines, hot);
  const dot = document.getElementById("shot");
  if (e && e.shot_zone && ZONE[e.shot_zone]) {
    const xy = ZONE[e.shot_zone];
    const j = (index % 5) - 2;
    dot.setAttribute("cx", xy[0] + j * 8);
    dot.setAttribute("cy", xy[1] + (index % 3) * 6);
    dot.setAttribute("fill", e.shot_made ? "#3dd68c" : "#ff5a6a");
    dot.setAttribute("opacity", "1");
  } else {
    dot.setAttribute("opacity", "0");
  }
  drawWp(index, homeWp);
  const scrub = document.getElementById("scrub");
  scrub.max = String(events.length);
  scrub.value = String(index + 1);
}
function drawWp(index) {
  const svg = document.getElementById("wpchart");
  const n = Math.max(1, events.length);
  const pts = [[0, 36]];
  for (let i = 0; i <= index && i < events.length; i++) {
    const wp = events[i].home_win_prob == null ? 0.5 : events[i].home_win_prob;
    pts.push([((i + 1) / n) * 600, 8 + (1 - wp) * 56]);
  }
  const poly = pts.map(p => p[0].toFixed(1) + "," + p[1].toFixed(1)).join(" ");
  const last = pts[pts.length - 1];
  svg.innerHTML = "<path d=\\"M0,36 L600,36\\" stroke=\\"#31445f\\" stroke-dasharray=\\"4 4\\"/>"
    + "<polyline fill=\\"none\\" stroke=\\"#7eb6ff\\" stroke-width=\\"2\\" points=\\"" + poly + "\\"/>"
    + "<circle cx=\\"" + last[0].toFixed(1) + "\\" cy=\\"" + last[1].toFixed(1) + "\\" r=\\"3\\" fill=\\"#f5c451\\"/>";
}
function stop() {
  if (timer) clearInterval(timer);
  timer = null;
  document.getElementById("play").textContent = "Play";
}
function play() {
  if (timer) { stop(); return; }
  if (!events.length) return;
  if (cursor >= events.length - 1) cursor = -1;
  document.getElementById("play").textContent = "Pause";
  timer = setInterval(() => {
    cursor += 1;
    if (cursor >= events.length) { cursor = events.length - 1; render(cursor); stop(); return; }
    render(cursor);
  }, stepMs);
}
document.getElementById("play").addEventListener("click", play);
document.querySelectorAll(".spd").forEach(btn => btn.addEventListener("click", () => {
  document.querySelectorAll(".spd").forEach(b => b.classList.remove("on"));
  btn.classList.add("on");
  stepMs = 160 / Number(btn.dataset.speed);
  if (timer) { stop(); play(); }
}));
document.getElementById("scrub").addEventListener("input", (ev) => {
  stop();
  cursor = Number(ev.target.value) - 1;
  render(cursor);
});
document.getElementById("kicker").textContent = "Most representative of " + (GAME.simulated_runs || 0).toLocaleString() + " simulated games";
document.getElementById("away-name").textContent = away;
document.getElementById("home-name").textContent = home;
document.getElementById("away-head").textContent = away;
document.getElementById("home-head").textContent = home;
document.getElementById("away-score").style.color = COLOR[away] || "#f2c14e";
document.getElementById("home-score").style.color = COLOR[home] || "#7eb6ff";
const fit = GAME.fit || {};
document.getElementById("fit").textContent = fit.margin == null ? "" :
  ("Margin " + fit.margin + " (median " + fit.median_margin + "), total " + fit.total + " (median " + fit.median_total + ")");
render(-1);
</script>
</body></html>
"""
