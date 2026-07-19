#!/usr/bin/env python3
"""
Daily sync for the Scratcher Odds Ledger.

Combines two official Texas Lottery sources:
  1. The public CSV -- authoritative price/prize/remaining-prize counts, one row per
     prize tier per game.
  2. Each game's own detail page -- the actual source of "overall odds," which Texas
     Lottery publishes per game but not in the bulk CSV. The game list page links every
     game number to its detail page; this script visits each one and pulls the odds
     sentence directly.

This avoids depending on third-party trackers (which may rate-limit or block automated
requests) since the data comes straight from texaslottery.com in both cases.

Games are matched between the two by game number -- Texas Lottery reuses game *names*
across different eras, so numbers are the only reliable key.

Output: data.json, matching the ledger's import schema.

Usage:
    python sync_scratchers.py > data.json
"""
import csv
import io
import json
import re
import sys
import time
import urllib.request
from datetime import date

CSV_URL = "https://www.texaslottery.com/export/sites/lottery/Games/Scratch_Offs/scratchoff.csv"
GAME_LIST_URL = "https://www.texaslottery.com/export/sites/lottery/Games/Scratch_Offs/all.html"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ScratcherLedgerSync/1.0)"}

# Guaranteed baseline: verified "1 in X" overall odds, confirmed against official filings
# by hand. Used only if a game's own detail page can't be reached or parsed for some reason --
# the live per-game scrape below is the primary source now, since it's first-party and doesn't
# depend on a third-party tracker that may block automated requests.
ODDS_OVERRIDES = {
    2613: 3.41,
    2689: 3.45,
    2744: 3.99,
    2627: 3.89,
    2713: 3.98,
    2622: 4.33,
    2711: 4.39,
    2624: 3.66,
    2665: 3.91,
    2587: 3.23,
    2589: 3.36,
    2400: 3.49,
}


def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_prize_data(csv_text):
    """For each game number, keep only the highest-value ('top') prize row."""
    reader = csv.DictReader(io.StringIO(csv_text.split("\n", 1)[1]))  # skip title line
    best = {}
    for row in reader:
        try:
            game_num = int(row["Game Number"])
            level = row["Prize Level"].strip()
            if level.upper() == "TOTAL":
                continue
            prize_amount = float(level.replace("$", "").replace(",", ""))
            total = int(row["Total Prizes in Level"].replace(",", ""))
            claimed_raw = row["Prizes Claimed"].strip().replace(",", "")
            claimed = int(claimed_raw) if claimed_raw not in ("", "---") else 0
            name = row["Game Name"].strip()
            price = row.get("Ticket Price", "").strip()
        except (KeyError, ValueError):
            continue

        current = best.get(game_num)
        if current is None or prize_amount > current["prize"]:
            best[game_num] = {
                "name": name,
                "gameNumber": game_num,
                "price": float(price) if price else None,
                "prize": prize_amount,
                "total": total,
                "remain": max(total - claimed, 0),
            }
    return best


def get_detail_page_links(html):
    """
    Extract (game_number -> absolute detail page URL) from the official game list page.
    Texas Lottery links each game number directly to its own detail page, e.g.
    <a href="/export/.../details.html_252699703.html">2613</a> -- the link TEXT is the
    game number, which is the only reliable identifier (names get reused across eras).
    """
    links = {}
    pattern = re.compile(
        r'<a[^>]+href="([^"]*details\.html_\d+\.html)"[^>]*>\s*(\d{3,4})\s*</a>',
        re.IGNORECASE
    )
    for href, game_num_str in pattern.findall(html):
        url = href if href.startswith("http") else "https://www.texaslottery.com" + href
        links[int(game_num_str)] = url
    return links


def extract_odds_from_detail_page(html):
    """Pull the '1 in X' overall odds figure out of a game's own detail page."""
    match = re.search(
        r"overall odds[^0-9]{0,80}1\s*in\s*([0-9]+(?:\.[0-9]+)?)",
        html,
        re.IGNORECASE
    )
    return float(match.group(1)) if match else None


def fetch_official_odds(game_numbers, delay=0.3):
    """
    For each game number, find its detail page and scrape the real overall odds off it --
    the actual first-party Texas Lottery source, not a third-party aggregator.
    """
    odds = {}
    today = date.today().isoformat()
    try:
        list_html = fetch(GAME_LIST_URL)
        links = get_detail_page_links(list_html)
    except Exception as e:
        print(f"WARNING could not load game list page: {e}", file=sys.stderr)
        return odds

    for game_num in game_numbers:
        url = links.get(game_num)
        if not url:
            continue
        try:
            detail_html = fetch(url)
            val = extract_odds_from_detail_page(detail_html)
            if val is not None:
                odds[game_num] = {"odds": val, "oddsAsOf": today}
        except Exception as e:
            print(f"WARNING could not fetch odds for game {game_num}: {e}", file=sys.stderr)
        time.sleep(delay)  # be polite to their server
    return odds


def main():
    try:
        csv_text = fetch(CSV_URL)
        prize_data = parse_prize_data(csv_text)
    except Exception as e:
        print(f"ERROR fetching official prize data: {e}", file=sys.stderr)
        prize_data = {}

    odds_data = fetch_official_odds(prize_data.keys())

    today = date.today().isoformat()
    output = []
    for game_num, g in prize_data.items():
        g["asOf"] = today
        odds_info = odds_data.get(game_num)
        if odds_info:
            g["odds"] = odds_info["odds"]
            g["oddsAsOf"] = odds_info["oddsAsOf"]
        elif game_num in ODDS_OVERRIDES:
            g["odds"] = ODDS_OVERRIDES[game_num]
            g["oddsAsOf"] = "verified manually"
        else:
            g["odds"] = None
            g["oddsAsOf"] = None
        output.append(g)

    output.sort(key=lambda g: g["name"])
    json.dump(output, sys.stdout, indent=2)
    print(f"\nWrote {len(output)} games ({sum(1 for g in output if g['odds'])} with odds)", file=sys.stderr)


if __name__ == "__main__":
    main()
