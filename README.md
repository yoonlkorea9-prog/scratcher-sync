# Scratcher Sync

Daily automated pull of Texas Lottery scratch-off data (top prize, price, and how many
top prizes remain per game), formatted for import into the **Scratcher Odds Ledger**
artifact.

Runs itself once a day via GitHub Actions and commits the refreshed `data.json` to this
repo. No server, database, or hosting to maintain.

## How it works

1. `sync_scratchers.py` loads the official game list page, follows the hyperlink for
   every active game to that game's own detail page, and parses everything off it in
   one pass: overall odds, the prize/claimed table, the "Prizes Claimed as of [date]"
   line, ticket price, and the ticket's own image URL.
2. `.github/workflows/daily-sync.yml` runs that script every day on a schedule and
   commits the result as `data.json`.
3. Anything (like the ledger artifact) can fetch the current data with a plain HTTP
   request to:

   ```
   https://raw.githubusercontent.com/<your-username>/<this-repo>/main/data.json
   ```

Earlier versions of this script tried the bulk CSV Texas Lottery publishes plus a
third-party odds-tracking site. Both had real problems: the bulk CSV lags behind
newly-launched games (a game can have a live detail page days before it's added to the
CSV), and the third-party site blocked automated requests outright. Scraping each
game's own official page directly avoids both issues and is the actual first-party
source for all of this data.

## One-time setup

1. Push this repo to GitHub. **Keep it public** — `raw.githubusercontent.com` only
   serves private-repo files with an auth token, which isn't safe to embed in a
   browser-side tool. None of this data is sensitive; it's all already public on
   texaslottery.com.
2. Go to the **Actions** tab → **Daily scratcher sync** → **Run workflow** to trigger
   the first run manually (don't wait for the schedule).
3. Once `data.json` appears, click it → **Raw**, copy the URL, and paste it into the
   ledger's "Live data source URL" field.

## Data format

```json
[
  {
    "name": "$1,000,000 Crossword",
    "gameNumber": 2753,
    "price": 20,
    "prize": 1000000,
    "total": 6,
    "remain": 6,
    "asOf": "2026-07-18",
    "odds": 3.41,
    "oddsAsOf": "2026-07-18",
    "imageUrl": "https://www.texaslottery.com/export/sites/lottery/Images/scratchoffs/2753_img1.gif"
  }
]
```

Every field comes from the same source: that specific game's own detail page on
texaslottery.com, fetched fresh each run. `asOf` is *that game's* own "Prizes Claimed
as of" date -- these can differ slightly game to game, since Texas Lottery doesn't
necessarily update every game's page on the same day.

Games are matched by `gameNumber`, not name -- Texas Lottery reuses names across
different games released years apart, so name-matching alone is unreliable.

`ODDS_OVERRIDES` in the script is a small hand-verified fallback, used only if a
specific game's page can't be reached or parsed on a given run.

## Notes

- Schedule defaults to 12:00 UTC (~7am Central) — edit the `cron` line in the workflow
  file to change it.
- This is a personal data-tracking tool, not affiliated with or endorsed by the Texas
  Lottery Commission.
- Scratch-off games involve real financial risk. See
  [texaslottery.com/responsible-gambling](https://www.texaslottery.com/export/sites/lottery/Social_Responsibility/responsible_gambling/index.html)
  or call 1-800-522-4700 for confidential support.

## License

MIT — see [LICENSE](LICENSE).
