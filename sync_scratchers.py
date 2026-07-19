#!/usr/bin/env python3
"""
Daily sync for the Scratcher Odds Ledger.

Combines two sources:
  1. Texas Lottery's official CSV -- authoritative price/prize/remaining-prize counts.
  2. ScratchSmarter's public Texas scratch-games table -- overall odds (not published
     in the official CSV) plus a per-game "last scraped" date, since ScratchSmarter
     doesn't refresh every game on the same day.

Output: data.json, matching the ledger's import schema. Games are matched between the
two sources by game number, since Texas Lottery reuses game *names* across different
eras (confirmed multiple times while building this) -- numbers are the only reliable key.

Usage:
    python sync_scratchers.py > data.json
"""
import csv
import io
import json
import re
import sys
import urllib.request
from datetime import date

CSV_URL = "https://www.texaslottery.com/export/sites/lottery/Games/Scratch_Offs/scratchoff.csv"
ODDS_TABLE_URL = "https://scratchsmarter.com/texas/scratch-games/"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ScratcherLedgerSync/1.0)"}

# Guaranteed baseline: verified "1 in X" overall odds, confirmed against official filings
# or third-party trackers by hand. This always applies regardless of whether the scrape
# below succeeds, since sites like ScratchSmarter can (and did) block automated requests
# with a 403 -- scraping is treated as a bonus on top of this, never the only source.
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


def parse_odds_table(html):
    """
    Extract (game_number -> {odds, oddsAsOf}) from ScratchSmarter's table.
    Uses a lightweight regex over <tr>...</tr> blocks rather than a full HTML parser,
    to avoid an extra dependency -- tolerant of attribute/whitespace changes but does
    assume the column order: PRICE | NAME | OVERALL ODDS | TOP PRIZES LEFT | NUMBER | SCRAPE DATE.
    """
    odds = {}
    row_re = re.compile(r"<tr[^>]*>(.*?)</tr>", re.DOTALL | re.IGNORECASE)
    cell_re = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.DOTALL | re.IGNORECASE)
    tag_re = re.compile(r"<[^>]+>")

    for row_match in row_re.finditer(html):
        cells = cell_re.findall(row_match.group(1))
        if len(cells) < 6:
            continue
        clean = [tag_re.sub("", c).strip() for c in cells]
        odds_val, game_num_val, date_val = clean[2], clean[4], clean[5]
        try:
            game_num = int(game_num_val)
            odds_num = float(odds_val)
        except ValueError:
            continue
        # ScratchSmarter date format observed as YYYY-MM-DD; keep as-is if it matches, else skip.
        as_of = date_val if re.match(r"^\d{4}-\d{2}-\d{2}$", date_val) else None
        odds[game_num] = {"odds": odds_num, "oddsAsOf": as_of}
    return odds


def main():
    try:
        csv_text = fetch(CSV_URL)
        prize_data = parse_prize_data(csv_text)
    except Exception as e:
        print(f"ERROR fetching official prize data: {e}", file=sys.stderr)
        prize_data = {}

    try:
        odds_html = fetch(ODDS_TABLE_URL)
        odds_data = parse_odds_table(odds_html)
    except Exception as e:
        print(f"WARNING fetching odds table (continuing without odds): {e}", file=sys.stderr)
        odds_data = {}

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
