#!/usr/bin/env python3
"""
Pulls the Texas Lottery's official daily "Prizes Claimed" CSV and converts
the top-prize tier of each game into JSON the Scratcher Odds Ledger can import.

Usage:
    python sync_scratchers.py > data.json

Intended to run daily via a GitHub Actions cron job (see .github/workflows/daily-sync.yml).
Source: https://www.texaslottery.com/export/sites/lottery/Games/Scratch_Offs/scratchoff.csv

Note: this CSV does not include "overall odds" -- that's only published on each
game's individual page. Odds entered manually (or via ODDS_OVERRIDES below) are
preserved; this script only ever updates price / prize / remain / total / asOf.
"""
import csv
import io
import json
import sys
import urllib.request
from collections import defaultdict
from datetime import date

CSV_URL = "https://www.texaslottery.com/export/sites/lottery/Games/Scratch_Offs/scratchoff.csv"

# Optional: paste verified "1 in X" overall odds here as you find them (game_number: odds).
# These get merged into the output so odds aren't lost between runs.
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


def fetch_csv():
    req = urllib.request.Request(CSV_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_top_tier(csv_text):
    """For each game number, keep only the highest-value prize row."""
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


def main():
    csv_text = fetch_csv()
    games = parse_top_tier(csv_text)

    today = date.today().isoformat()
    output = []
    for game_num, g in games.items():
        g["asOf"] = today
        g["odds"] = ODDS_OVERRIDES.get(game_num)
        output.append(g)

    output.sort(key=lambda g: g["name"])
    json.dump(output, sys.stdout, indent=2)


if __name__ == "__main__":
    main()
