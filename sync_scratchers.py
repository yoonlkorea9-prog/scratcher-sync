#!/usr/bin/env python3
"""
Daily sync for the Scratcher Odds Ledger.

Follows the same workflow a person would use by hand:
  1. Load the official game list: texaslottery.com/.../Scratch_Offs/all.html
  2. Find each game's hyperlink (its own detail page)
  3. Visit that detail page
  4. Parse everything off it: overall odds, the prize/claimed table, the
     "Prizes Claimed as of [date]" line, and the ticket image URL

This replaces an earlier version that combined the bulk CSV (which lags behind
newly-launched games) with a third-party odds site (which blocked automated
requests). Pulling everything from each game's own official page fixes both:
every game listed on the site gets picked up the same day it appears there,
and there's no dependency on anything but texaslottery.com itself.

Usage:
    python sync_scratchers.py > data.json
"""
import html as html_lib
import json
import re
import sys
import time
import urllib.request
from datetime import date, datetime

GAME_LIST_URL = "https://www.texaslottery.com/export/sites/lottery/Games/Scratch_Offs/all.html"
BASE = "https://www.texaslottery.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ScratcherLedgerSync/1.0)"}
REQUEST_DELAY = 0.3  # seconds between requests, to be polite to their server

# Guaranteed fallback for a small number of hand-verified games, used only if a
# specific page can't be reached or parsed that day.
ODDS_OVERRIDES = {
    2613: 3.41,
    2753: 3.41,
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


def get_detail_page_links(list_html):
    """
    Game numbers are hyperlinked to their own detail page on the list page, e.g.
    <a href="/export/.../details.html_252698618.html">2753</a>. The link TEXT is
    the game number -- the only reliable identifier (names get reused over the years).
    """
    links = {}
    pattern = re.compile(
        r'<a[^>]+href="([^"]*details\.html_\d+\.html)"[^>]*>\s*(\d{3,4})\s*</a>',
        re.IGNORECASE
    )
    for href, game_num_str in pattern.findall(list_html):
        url = href if href.startswith("http") else BASE + href
        links[int(game_num_str)] = url
    return links


def parse_prize_table(html):
    """Pulls (amount, printed, claimed) rows out of the 'Prizes Printed' table."""
    rows = []
    row_re = re.compile(r"<tr[^>]*>(.*?)</tr>", re.DOTALL | re.IGNORECASE)
    cell_re = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.DOTALL | re.IGNORECASE)
    tag_re = re.compile(r"<[^>]+>")

    for row_match in row_re.finditer(html):
        cells = cell_re.findall(row_match.group(1))
        if len(cells) < 3:
            continue
        clean = [html_lib.unescape(tag_re.sub("", c)).strip() for c in cells[:3]]
        amount_str = clean[0].replace("$", "").replace(",", "").strip()
        printed_str = clean[1].replace(",", "").strip()
        claimed_str = clean[2].replace(",", "").strip()
        try:
            amount = float(amount_str)
            printed = int(printed_str)
        except ValueError:
            continue  # header row or something else entirely
        claimed = 0 if claimed_str in ("", "---", "\u2014") else (
            int(claimed_str) if claimed_str.isdigit() else 0
        )
        rows.append((amount, printed, claimed))
    return rows


def parse_detail_page(html, game_number):
    """Extracts everything the ledger needs from one game's detail page."""
    result = {"gameNumber": game_number}

    # Name + odds come from one sentence: "Overall odds of winning any prize in
    # {NAME} are 1 in {X}." -- reliable across every page checked so far.
    m = re.search(
        r"Overall odds of winning any prize in\s+(.+?)\s+are\s+1\s*in\s*([0-9]+(?:\.[0-9]+)?)",
        html, re.IGNORECASE | re.DOTALL
    )
    if m:
        result["name"] = html_lib.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip()
        result["odds"] = float(m.group(2))

    # Per-game "as of" date, e.g. "Prizes Claimed as of July 18, 2026."
    m = re.search(r"Prizes Claimed as of\s+([A-Za-z]+ \d{1,2},\s*\d{4})", html, re.IGNORECASE)
    if m:
        try:
            result["asOf"] = datetime.strptime(m.group(1).strip(), "%B %d, %Y").date().isoformat()
        except ValueError:
            pass

    # Ticket price, e.g. "$20 Dollar Game Game Features"
    m = re.search(r"\$?(\d+(?:\.\d+)?)\s*Dollar Game", html, re.IGNORECASE)
    if m:
        result["price"] = float(m.group(1))

    # Front ticket image
    m = re.search(r'(https://www\.texaslottery\.com/export/sites/lottery/Images/scratchoffs/\d+_img1\.\w+)', html)
    if not m:
        m = re.search(r'src="(/export/sites/lottery/Images/scratchoffs/\d+_img1\.\w+)"', html)
        if m:
            result["imageUrl"] = BASE + m.group(1)
    else:
        result["imageUrl"] = m.group(1)

    # Top prize tier from the "Prizes Printed" table
    rows = parse_prize_table(html)
    if rows:
        top = max(rows, key=lambda r: r[0])
        result["prize"] = top[0]
        result["total"] = top[1]
        result["remain"] = max(top[1] - top[2], 0)

    return result


def main():
    today = date.today().isoformat()
    try:
        list_html = fetch(GAME_LIST_URL)
        links = get_detail_page_links(list_html)
    except Exception as e:
        print(f"ERROR: could not load game list page: {e}", file=sys.stderr)
        sys.exit(1)

    output = []
    errors = 0
    for game_number, url in sorted(links.items()):
        try:
            detail_html = fetch(url)
            g = parse_detail_page(detail_html, game_number)

            if "odds" not in g and game_number in ODDS_OVERRIDES:
                g["odds"] = ODDS_OVERRIDES[game_number]
            g["oddsAsOf"] = g.get("asOf") if "odds" in g else None
            g.setdefault("asOf", today)
            g.setdefault("odds", None)

            # Skip anything we couldn't get the essentials for (name/price/prize).
            if "name" in g and "price" in g and "prize" in g:
                output.append(g)
            else:
                errors += 1
                print(f"WARNING: incomplete data for game {game_number}, skipped", file=sys.stderr)
        except Exception as e:
            errors += 1
            print(f"WARNING: failed on game {game_number} ({url}): {e}", file=sys.stderr)
        time.sleep(REQUEST_DELAY)

    output.sort(key=lambda g: g["name"])
    json.dump(output, sys.stdout, indent=2)
    with_odds = sum(1 for g in output if g["odds"])
    with_img = sum(1 for g in output if g.get("imageUrl"))
    print(f"\nWrote {len(output)} games ({with_odds} with odds, {with_img} with images, {errors} errors)", file=sys.stderr)


if __name__ == "__main__":
    main()
