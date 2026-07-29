#!/usr/bin/env python3
"""
Checks which scratch-off games are confirmed sold at a specific store chain in a
specific city -- e.g. "which games does 7-Eleven carry in Frisco, and where exactly?"

Uses Texas Lottery's own Scratch Ticket Locator (texaslottery.com/.../Retailer_Locator.jsp),
the same tool a person would use by hand: for each game, it submits a (city, game) search
via the locator's actual POST request and pulls out every matching retailer's name and
address. This inverts the locator's native "one game at a time" search into "all games at
this chain, in this city, with every location" -- which the site itself doesn't offer.

Not part of the daily sync -- this is location- and chain-specific, and checking one
combination means one POST request per game (~70+), so it's meant to be run on demand for
whichever city/chain you actually care about.

Usage:
    python check_store_availability.py --city FRISCO --chain "7-ELEVEN" --games-file data.json

Outputs:
    results.json  -- full structured data (every game, every matching location + address)
    summary.md    -- human-readable version with clickable Google Maps links per store
"""
import argparse
import html as html_lib
import json
import re
import sys
import time
import urllib.parse
import urllib.request

LOCATOR_URL = "https://www.texaslottery.com/opencms/Games/Scratch_Offs/Retailer_Locator.jsp"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ScratcherLedgerSync/1.0)",
    "Content-Type": "application/x-www-form-urlencoded",
}
REQUEST_DELAY = 0.4  # seconds between requests, to be polite to their server


def maps_url(name, address, city):
    """Universal Google Maps search-by-query link -- no API key needed, works everywhere."""
    query = f"{name}, {address}, {city}, TX"
    return "https://www.google.com/maps/search/?api=1&query=" + urllib.parse.quote(query)


def find_matches_for_game(city, game_number, chain_query):
    """
    POSTs one (city, game) search and returns every matching retailer as
    {name, address, mapsUrl} -- not just the first match.
    """
    data = urllib.parse.urlencode({
        "submitted": "true",
        "city": city,
        "zip": "",
        "gameNumber": str(game_number),
        "smoking": "",
        "selfCheck": "",
        "Submit": "Submit",
    }).encode()
    req = urllib.request.Request(LOCATOR_URL, data=data, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        html = resp.read().decode("utf-8", errors="replace")

    row_re = re.compile(r"<tr[^>]*>(.*?)</tr>", re.DOTALL | re.IGNORECASE)
    cell_re = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.DOTALL | re.IGNORECASE)
    tag_re = re.compile(r"<[^>]+>")

    # Retailer names appear inconsistently formatted ("7 ELEVEN" vs "7-ELEVEN"), so
    # normalize by stripping whitespace/hyphens before comparing.
    chain_norm = re.sub(r"[\s\-]", "", chain_query.upper())

    matches = []
    for row in row_re.findall(html):
        cells = cell_re.findall(row)
        # Table columns: Retailer Name | Street Address | City | Phone | Smoking | Self-Check | Type | Map
        if len(cells) < 3:
            continue
        clean = [html_lib.unescape(tag_re.sub("", c)).strip() for c in cells]
        name_cell, address_cell, city_cell = clean[0], clean[1], clean[2]
        name_norm = re.sub(r"[\s\-]", "", name_cell.upper())
        if chain_norm and chain_norm in name_norm:
            matches.append({
                "name": name_cell,
                "address": address_cell,
                "city": city_cell,
                "mapsUrl": maps_url(name_cell, address_cell, city_cell),
            })
    return matches


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--city", required=True, help="City as listed on texaslottery.com, e.g. FRISCO")
    parser.add_argument("--chain", required=True, help="Store chain name to match, e.g. '7-ELEVEN'")
    parser.add_argument("--games-file", required=True, help="Path to data.json from sync_scratchers.py")
    args = parser.parse_args()

    city = args.city.strip().upper()
    with open(args.games_file) as f:
        games = {g["gameNumber"]: g["name"] for g in json.load(f)}

    print(f"Checking {len(games)} games for '{args.chain}' in {city}...", file=sys.stderr)

    results = []
    for i, (game_number, name) in enumerate(sorted(games.items()), 1):
        try:
            locations = find_matches_for_game(city, game_number, args.chain)
            if locations:
                results.append({"gameNumber": game_number, "name": name, "locations": locations})
                print(f"  [{i}/{len(games)}] YES  {game_number} - {name}  ({len(locations)} location(s))", file=sys.stderr)
            else:
                print(f"  [{i}/{len(games)}] no   {game_number} - {name}", file=sys.stderr)
        except Exception as e:
            print(f"  [{i}/{len(games)}] WARNING: game {game_number} failed: {e}", file=sys.stderr)
        time.sleep(REQUEST_DELAY)

    with open("results.json", "w") as f:
        json.dump(results, f, indent=2)

    total_locations = sum(len(g["locations"]) for g in results)
    with open("summary.md", "w") as f:
        f.write(f"## Games sold at '{args.chain}' in {city}\n\n")
        if not results:
            f.write(f"No games matched '{args.chain}' in {city}.\n")
        else:
            f.write(f"**{len(results)}** of **{len(games)}** games confirmed, across **{total_locations}** location(s).\n\n")
            for g in results:
                f.write(f"### {g['name']} (Game #{g['gameNumber']})\n\n")
                for loc in g["locations"]:
                    f.write(f"- [{loc['name']} \u2014 {loc['address']}, {loc['city']}]({loc['mapsUrl']})\n")
                f.write("\n")

    print(f"\n{len(results)} of {len(games)} games confirmed at '{args.chain}' locations in {city} "
          f"({total_locations} total locations)", file=sys.stderr)


if __name__ == "__main__":
    main()
