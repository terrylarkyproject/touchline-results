#!/usr/bin/env python3
"""Touchline Results updater.

Fetches finished matches from ESPN's public soccer endpoints and merges them
into data/results.json. Standard library only, so GitHub Actions needs no
installs. Never invents data: a field the source does not give is left out.

Env vars:
  LOOKBACK_DAYS  how many days back to check (default 4)
  BACKFILL_FROM  YYYY-MM-DD; if set, check from this date instead
"""
import json, os, re, sys, time, unicodedata, urllib.request, urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "results.json"
UK = ZoneInfo("Europe/London")
BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
STAND = "https://site.api.espn.com/apis/v2/sports/soccer"

LEAGUES = {  # ESPN code -> competition name used on the page
    "eng.1": "Premier League",
    "esp.1": "La Liga",
    "ita.1": "Serie A",
    "ger.1": "Bundesliga",
    "fra.1": "Ligue 1",
    "uefa.champions": "Champions League",
    "usa.1": "MLS",
    "fifa.world": "World Cup",
}

# ESPN name -> the name already used in the saved results
RENAME = {
    "Internazionale": "Inter",
    "Bournemouth": "AFC Bournemouth",
    "Brighton": "Brighton & Hove Albion",
    "Tottenham": "Tottenham Hotspur",
    "Wolves": "Wolverhampton Wanderers",
    "Newcastle": "Newcastle United",
    "Atletico de Madrid": "Atletico Madrid",
    "PSG": "Paris Saint-Germain",
}

STAT_MAP = [  # (label on page, ESPN stat name)
    ("Possession (%)", "possessionPct"),
    ("Shots", "totalShots"),
    ("Shots on target", "shotsOnTarget"),
    ("Corners", "wonCorners"),
    ("Fouls", "foulsCommitted"),
    ("Yellow cards", "yellowCards"),
    ("Offsides", "offsides"),
]


def log(*a):
    print(*a, flush=True)


def strip_accents(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def team_name(raw):
    n = strip_accents((raw or "").strip())
    return RENAME.get(n, n)


def slug(s):
    s = strip_accents(s).lower().replace("&", "and")
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    return re.sub(r"[\s-]+", "-", s).strip("-")


def doc_id(r):
    return f"{r['date']}-{slug(r['home'])}-v-{slug(r['away'])}"


def get(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (touchline-results)", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            log(f"  fetch failed ({i + 1}/{tries}): {url} -> {e}")
            if 400 <= e.code < 500 and e.code != 429:
                return None  # the request itself was refused; retrying won't help
            time.sleep(2 * (i + 1))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            log(f"  fetch failed ({i + 1}/{tries}): {url} -> {e}")
            time.sleep(2 * (i + 1))
    return None


def minute(clock):
    """'90'+3'' -> 90, '56'' -> 56. None if absent."""
    if not clock:
        return None
    m = re.match(r"\s*(\d+)", str(clock.get("displayValue") or ""))
    if m:
        return int(m.group(1))
    v = clock.get("value")
    return int(v // 60) + 1 if isinstance(v, (int, float)) and v > 0 else None


def num(v):
    try:
        f = float(str(v).replace("%", ""))
        return int(f) if f.is_integer() else f
    except (TypeError, ValueError):
        return None


SUB_RE = re.compile(r"Substitution,[^.]*\.\s*(.+?)\s+replaces\s+(.+?)(?:\s+(?:because|due)\b.*)?\.?\s*$", re.I)
ASSIST_RE = re.compile(r"Assisted by ([^.]+?)(?:\s+with\b|\s+following\b|\.|$)")


def parse_event(ev, comp_name):
    """Score-level record from a scoreboard event. None if not finished."""
    st = (ev.get("status") or {}).get("type") or {}
    if not st.get("completed"):
        return None
    c = (ev.get("competitions") or [{}])[0]
    sides = {x.get("homeAway"): x for x in c.get("competitors", [])}
    if "home" not in sides or "away" not in sides:
        return None
    h, a = sides["home"], sides["away"]
    hs, as_ = num(h.get("score")), num(a.get("score"))
    if hs is None or as_ is None:
        return None
    ko = datetime.fromisoformat(ev["date"].replace("Z", "+00:00")).astimezone(UK)
    hour = ko.strftime("%I").lstrip("0") or "12"
    rec = {
        "match_id": f"espn:{ev['id']}",
        "date": ko.strftime("%Y-%m-%d"),
        "kickoff": f"{ko.strftime('%a')} {ko.day} {ko.strftime('%b %Y')}, {hour}:{ko.strftime('%M')}{ko.strftime('%p').lower()}",
        "competition": comp_name,
        "home": team_name(h["team"].get("displayName")),
        "away": team_name(a["team"].get("displayName")),
        "home_score": hs,
        "away_score": as_,
    }
    ids = {str(h["team"].get("id")): rec["home"], str(a["team"].get("id")): rec["away"]}
    goals, reds = [], []
    for d in c.get("details", []) or []:
        tname = ids.get(str((d.get("team") or {}).get("id")))
        mn = minute(d.get("clock"))
        who = [x.get("displayName") for x in d.get("athletesInvolved", []) if x.get("displayName")]
        if d.get("scoringPlay") and not d.get("shootout"):
            g = {"min": mn, "team": tname}
            if who:
                g["scorer"] = who[0]
            if d.get("penaltyKick"):
                g["penalty"] = True
            if d.get("ownGoal"):
                g["own_goal"] = True
            goals.append({k: v for k, v in g.items() if v is not None})
        elif d.get("redCard"):
            r = {"min": mn, "team": tname}
            if who:
                r["player"] = who[0]
            reds.append({k: v for k, v in r.items() if v is not None})
    rec["goals"], rec["red_cards"] = goals, reds
    rec["_ids"] = ids
    return rec


def add_summary(rec, lg, event_id):
    """Adds stats, players, subs and assists. Returns True on success."""
    s = get(f"{BASE}/{lg}/summary?event={event_id}")
    if not s:
        return False
    ids = rec["_ids"]
    home_id = next(k for k, v in ids.items() if v == rec["home"])

    # Assists and any missing scorers from key-event commentary
    kes = s.get("keyEvents") or []
    goal_kes = [k for k in kes if k.get("scoringPlay") and "shootout" not in str((k.get("type") or {}).get("type", "")).lower()]
    for g in rec["goals"]:
        for k in goal_kes:
            if minute(k.get("clock")) == g.get("min") and ids.get(str((k.get("team") or {}).get("id"))) == g.get("team"):
                if "scorer" not in g:
                    ps = [p.get("athlete", {}).get("displayName") for p in k.get("participants", [])]
                    if ps and ps[0]:
                        g["scorer"] = ps[0]
                m = ASSIST_RE.search(k.get("text") or "")
                if m and "assist" not in g:
                    g["assist"] = m.group(1).strip()
                break

    # Substitutions: minutes per team, plus who came on and off where the feed says
    subs = {rec["home"]: [], rec["away"]: []}
    detail = []
    for k in kes:
        if "substitution" in str((k.get("type") or {}).get("type", "")).lower():
            t = ids.get(str((k.get("team") or {}).get("id")))
            mn = minute(k.get("clock"))
            if t in subs and mn is not None:
                subs[t].append(mn)
                m = SUB_RE.search(k.get("text") or "")
                if m:
                    detail.append({"min": mn, "team": t, "on": m.group(1).strip(), "off": m.group(2).strip()})
    rec["subs"] = [{"team": t, "mins": sorted(m)} for t, m in subs.items()]
    rec["subs_detail"] = sorted(detail, key=lambda d: d["min"])

    # Team stats
    by_team = {}
    for t in (s.get("boxscore") or {}).get("teams", []) or []:
        tid = str((t.get("team") or {}).get("id"))
        by_team[tid] = {x.get("name"): x.get("displayValue") for x in t.get("statistics", []) or []}
    away_id = next((k for k in ids if k != home_id), None)
    stats = []
    if home_id in by_team and away_id in by_team:
        for label, key in STAT_MAP:
            hv, av = num(by_team[home_id].get(key)), num(by_team[away_id].get(key))
            if hv is not None and av is not None:
                stats.append({"label": label, "home": hv, "away": av})
    rec["stats"] = stats

    # Players who appeared (starters, then used substitutes)
    players = []
    for team in (s.get("rosters") or []):
        tname = ids.get(str((team.get("team") or {}).get("id")))
        if not tname:
            continue
        ro = team.get("roster") or []
        names = [p["athlete"]["displayName"] for p in ro if p.get("starter") and p.get("athlete", {}).get("displayName")]
        names += [p["athlete"]["displayName"] for p in ro if not p.get("starter") and p.get("subbedIn") and p.get("athlete", {}).get("displayName")]
        players.append({"team": tname, "names": names})
    players.sort(key=lambda x: 0 if x["team"] == rec["home"] else 1)
    rec["players"] = players
    return bool(stats or players)


def same_match(a, b):
    """Fuzzy match for records saved under slightly different team names."""
    if a.get("date") != b.get("date") or a.get("competition") != b.get("competition"):
        return False
    if (a.get("home_score"), a.get("away_score")) != (b.get("home_score"), b.get("away_score")):
        return False
    def toks(n):
        return {t for t in slug(n).split("-") if len(t) > 2 and t not in {"fc", "afc", "city", "united", "real"}} or set(slug(n).split("-"))
    return bool(toks(a["home"]) & toks(b["home"])) and bool(toks(a["away"]) & toks(b["away"]))


def merge(old, new):
    """New feed data wins, but keep names/assists/sources added by hand."""
    out = dict(new)
    for g in out.get("goals", []):
        for og in old.get("goals", []):
            if og.get("min") == g.get("min") and og.get("team") == g.get("team"):
                for k in ("scorer", "assist", "penalty", "own_goal"):
                    if k in og and k not in g:
                        g[k] = og[k]
                break
    for r in out.get("red_cards", []):
        for orc in old.get("red_cards", []):
            if orc.get("team") == r.get("team") and abs((orc.get("min") or 0) - (r.get("min") or 0)) <= 8 and "player" in orc and "player" not in r:
                r["player"] = orc["player"]
    for k in ("details_source", "notes"):
        if k in old and k not in out:
            out[k] = old[k]
    for k in ("subs", "subs_detail", "stats", "players"):
        if not out.get(k) and old.get(k):
            out[k] = old[k]
    return out


def complete(r):
    return bool(r.get("stats")) and not r.get("stats_pending") and "subs_detail" in r and all("scorer" in g for g in r.get("goals", []))


def fetch_events(lg, start_d, end_d):
    """All scoreboard events between two dates, asked for a week at a time.
    A week the feed refuses is retried one day at a time. Returns None only
    if every request failed."""
    events, seen, ok = [], set(), False
    d = start_d
    while d <= end_d:
        w_end = min(d + timedelta(days=6), end_d)
        span = f"{d:%Y%m%d}" if d == w_end else f"{d:%Y%m%d}-{w_end:%Y%m%d}"
        sb = get(f"{BASE}/{lg}/scoreboard?dates={span}&limit=200", tries=2)
        chunks = [sb] if sb is not None else []
        if sb is None and d != w_end:
            day = d
            while day <= w_end:
                one = get(f"{BASE}/{lg}/scoreboard?dates={day:%Y%m%d}", tries=2)
                if one is not None:
                    chunks.append(one)
                day += timedelta(days=1)
                time.sleep(0.2)
        for c in chunks:
            ok = True
            for ev in c.get("events") or []:
                if ev.get("id") not in seen:
                    seen.add(ev.get("id"))
                    events.append(ev)
        d = w_end + timedelta(days=1)
        time.sleep(0.3)
    return events if ok else None


def fetch_tables(lg, comp):
    """Current league table(s) from ESPN standings. None if the feed fails."""
    d = get(f"{STAND}/{lg}/standings", tries=2)
    if not d:
        return None
    out = []
    for ch in (d.get("children") or [d]):
        rows = []
        for e in ((ch.get("standings") or {}).get("entries") or []):
            name = team_name((e.get("team") or {}).get("displayName"))
            st = {x.get("name"): x.get("value") for x in (e.get("stats") or [])}
            pts, gp = num(st.get("points")), num(st.get("gamesPlayed"))
            if not name or pts is None or gp is None:
                continue
            rows.append({"pos": num(st.get("rank")), "team": name, "p": gp, "w": num(st.get("wins")),
                         "d": num(st.get("ties")), "l": num(st.get("losses")),
                         "gd": num(st.get("pointDifferential")), "pts": pts})
        if len(rows) >= 8:
            rows.sort(key=lambda r: (r["pos"] if r["pos"] is not None else 99, -r["pts"]))
            for i, r in enumerate(rows, 1):
                if r["pos"] is None:
                    r["pos"] = i
            out.append({"competition": comp, "group": ch.get("name") or "", "rows": rows})
    return out


def fetch_fixtures(lg, comp, today):
    """Matches not yet played in the next 10 days. None if the feed fails."""
    events = fetch_events(lg, today, today + timedelta(days=10))
    if events is None:
        return None
    out = []
    for ev in events:
        st = (ev.get("status") or {}).get("type") or {}
        if st.get("completed") or st.get("state") not in (None, "pre"):
            continue
        c = (ev.get("competitions") or [{}])[0]
        sides = {x.get("homeAway"): x for x in c.get("competitors", [])}
        if "home" not in sides or "away" not in sides:
            continue
        try:
            ko = datetime.fromisoformat(ev["date"].replace("Z", "+00:00")).astimezone(UK)
        except Exception:
            continue
        hour = ko.strftime("%I").lstrip("0") or "12"
        out.append({"competition": comp, "date": ko.strftime("%Y-%m-%d"),
                    "kickoff": f"{ko.strftime('%a')} {ko.day} {ko.strftime('%b')}, {hour}:{ko.strftime('%M')}{ko.strftime('%p').lower()}",
                    "home": team_name(sides["home"]["team"].get("displayName")),
                    "away": team_name(sides["away"]["team"].get("displayName"))})
    return out


def main():
    now = datetime.now(timezone.utc)
    store = json.loads(DATA.read_text()) if DATA.exists() else {"results": []}
    results = {doc_id(r): r for r in store.get("results", [])}
    start = os.environ.get("BACKFILL_FROM", "").strip()
    start_d = datetime.strptime(start, "%Y-%m-%d").date() if start else (now - timedelta(days=int(os.environ.get("LOOKBACK_DAYS", "4")))).date()
    end_d = now.date()
    log(f"Checking {start_d} to {end_d}")
    added = updated = 0
    failures = []

    for lg, comp in LEAGUES.items():
        events = fetch_events(lg, start_d, end_d)
        if events is None:
            failures.append(comp)
            continue
        log(f"{comp}: {len(events)} events")
        for ev in events:
            rec = parse_event(ev, comp)
            if not rec:
                continue
            did = doc_id(rec)
            old = results.get(did) or next((v for v in results.values() if same_match(v, rec)), None)
            if old and complete(old) and old.get("match_id", "").startswith("espn:"):
                continue  # already fully filled from this feed
            got_summary = add_summary(rec, lg, ev["id"])
            time.sleep(0.4)
            rec.pop("_ids", None)
            rec.setdefault("subs", []); rec.setdefault("stats", []); rec.setdefault("players", [])
            if not got_summary:
                rec["stats_pending"] = True
            rec["source"] = "ESPN public scoreboard and match summary"
            rec["fetched_at"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
            if old:
                for k, v in list(results.items()):
                    if v is old:
                        del results[k]
                rec = merge(old, rec)
                updated += 1
            else:
                added += 1
            results[doc_id(rec)] = rec

    # Tables and upcoming fixtures: replaced each run; a league that fails keeps its last copy
    old_tables, old_fixtures = store.get("tables", []), store.get("fixtures", [])
    tables, fixtures = [], []
    for lg, comp in LEAGUES.items():
        if lg != "fifa.world":
            t = fetch_tables(lg, comp)
            tables += t if t is not None else [x for x in old_tables if x.get("competition") == comp]
        f = fetch_fixtures(lg, comp, now.astimezone(UK).date())
        fixtures += f if f is not None else [x for x in old_fixtures if x.get("competition") == comp and x.get("date", "") >= str(now.date())]
    fixtures.sort(key=lambda x: (x["date"], x["kickoff"]))
    log(f"Tables: {len(tables)}; upcoming fixtures: {len(fixtures)}")

    ordered = sorted(results.values(), key=lambda r: (r.get("date", ""), r.get("competition", ""), r.get("home", "")), reverse=True)
    changed = bool(added or updated) or tables != old_tables or fixtures != old_fixtures
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ") if changed else store.get("updated_at", now.strftime("%Y-%m-%dT%H:%M:%SZ"))
    store = {"updated_at": stamp, "tables_at": now.strftime("%Y-%m-%d") if tables != old_tables or not store.get("tables_at") else store["tables_at"],
             "count": len(ordered), "results": ordered, "tables": tables, "fixtures": fixtures}
    DATA.parent.mkdir(parents=True, exist_ok=True)
    DATA.write_text(json.dumps(store, ensure_ascii=False, indent=1) + "\n")
    log(f"Done: {added} added, {updated} updated, {len(ordered)} total.")
    if failures:
        log(f"Leagues that could not be fetched: {', '.join(failures)}")
    if len(failures) == len(LEAGUES):
        sys.exit("Every league failed to fetch - the feed may be down or blocked.")


if __name__ == "__main__":
    main()
