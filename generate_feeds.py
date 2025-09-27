#!/usr/bin/env python3
"""
generate_feeds.py
Generates:
 - docs/feeds/daily.xml  -> today's games
 - docs/feeds/season.xml -> upcoming games from the requested season
Requires: requests
Usage:
  export BALLDONTLIE_API_KEY="your_key_here"
  python generate_feeds.py --season-year 2025
"""

import os
import requests
import datetime
import time
import argparse
import html

API_BASE = "https://api.balldontlie.io/v1/games"

def rfc2822(dt):
    return dt.strftime("%a, %d %b %Y %H:%M:%S %z")

def parse_iso_to_dt(iso_str):
    # balldontlie returns e.g. "2025-09-28T19:30:00.000Z"
    s = iso_str.replace("Z", "+00:00")
    return datetime.datetime.fromisoformat(s)

def fetch_games(params, api_key):
    headers = {"Authorization": api_key}
    all_games = []
    # API uses cursor-based pagination; request per_page=100
    params = dict(params)
    params["per_page"] = 100
    while True:
        resp = requests.get(API_BASE, params=params, headers=headers, timeout=30)
        resp.raise_for_status()
        j = resp.json()
        data = j.get("data", [])
        all_games.extend(data)
        meta = j.get("meta", {})
        nxt = meta.get("next_cursor")
        if not nxt:
            break
        params["cursor"] = nxt
        # gentle sleep to avoid rate limit spikes
        time.sleep(0.2)
    return all_games

def build_rss(title, link, description, items):
    out = []
    out.append('<?xml version="1.0" encoding="utf-8"?>')
    out.append('<rss version="2.0">')
    out.append("<channel>")
    out.append(f"<title>{html.escape(title)}</title>")
    out.append(f"<link>{html.escape(link)}</link>")
    out.append(f"<description>{html.escape(description)}</description>")
    for it in items:
        out.append("  <item>")
        out.append(f"    <title>{html.escape(it['title'])}</title>")
        out.append(f"    <link>{html.escape(it['link'])}</link>")
        out.append(f"    <guid isPermaLink=\"false\">{html.escape(str(it['guid']))}</guid>")
        out.append(f"    <description>{html.escape(it['description'])}</description>")
        out.append(f"    <pubDate>{html.escape(it['pubDate'])}</pubDate>")
        out.append("  </item>")
    out.append("</channel>")
    out.append("</rss>")
    return "\n".join(out)

def make_game_item(game):
    gid = game["id"]
    visitor = game["visitor_team"]["full_name"]
    home = game["home_team"]["full_name"]
    title = f"{visitor} at {home}"
    dt = parse_iso_to_dt(game["date"])  # timezone-aware UTC
    pubDate = rfc2822(dt)
    # link - generic NBA game link (works as a pointer)
    link = f"https://www.nba.com/game/{gid}"
    description = f"Status: {game['status']} | Tip-off (UTC): {dt.strftime('%Y-%m-%d %H:%M:%S %Z')}"
    return {
        "title": title,
        "link": link,
        "guid": f"balldontlie-game-{gid}",
        "description": description,
        "pubDate": pubDate
    }

def ensure_dir(path):
    os.makedirs(path, exist_ok=True)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="docs/feeds", help="output directory (default: docs/feeds)")
    parser.add_argument("--season-year", type=int, default=datetime.date.today().year, help="season year (e.g. 2025)")
    args = parser.parse_args()

    api_key = os.environ.get("BALLDONTLIE_API_KEY")
    if not api_key:
        print("ERROR: set BALLDONTLIE_API_KEY environment variable")
        return 1

    ensure_dir(args.output_dir)

    today = datetime.date.today().isoformat()
    # 1) daily feed
    print(f"Fetching games for {today} ...")
    daily_games = fetch_games({"start_date": today, "end_date": today}, api_key)
    daily_items = [make_game_item(g) for g in daily_games]
    daily_rss = build_rss(
        title=f"NBA Gameday Feed - {today}",
        link="https://www.nba.com/schedule",
        description=f"NBA games for {today}",
        items=daily_items
    )
    with open(os.path.join(args.output_dir, "daily.xml"), "w", encoding="utf-8") as f:
        f.write(daily_rss)
    print(f"Wrote {len(daily_items)} items to {args.output_dir}/daily.xml")

    # 2) season feed (upcoming games from season)
    print(f"Fetching season {args.season_year} ...")
    season_games = fetch_games({"seasons[]": args.season_year}, api_key)
    # keep upcoming games only (>= today)
    now = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)
    upcoming = [g for g in season_games if parse_iso_to_dt(g["date"]) >= now]
    upcoming.sort(key=lambda g: g["date"])
    season_items = [make_game_item(g) for g in upcoming]
    season_rss = build_rss(
        title=f"NBA Upcoming Games - Season {args.season_year}",
        link="https://www.nba.com/schedule",
        description=f"Upcoming NBA games for season {args.season_year}",
        items=season_items
    )
    with open(os.path.join(args.output_dir, "season.xml"), "w", encoding="utf-8") as f:
        f.write(season_rss)
    print(f"Wrote {len(season_items)} items to {args.output_dir}/season.xml")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
