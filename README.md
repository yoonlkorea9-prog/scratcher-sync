# Scratcher Sync

Daily automated pull of Texas Lottery scratch-off data (top prize, price, and how many
top prizes remain per game), formatted for import into the **Scratcher Odds Ledger**
artifact.

Runs itself once a day via GitHub Actions and commits the refreshed `data.json` to this
repo. No server, database, or hosting to maintain.

## How it works

1. `sync_scratchers.py` downloads the Texas Lottery's official public CSV
   (`scratchoff.csv`), keeps only the highest-value ("top") prize tier for each active
   game, and computes how many of those top prizes are still unclaimed.
2. `.github/workflows/daily-sync.yml` runs that script every day on a schedule and
   commits the result as `data.json`.
3. Anything (like the ledger artifact) can fetch the current data with a plain HTTP
   request to:

   ```
   https://raw.githubusercontent.com/<your-username>/<this-repo>/main/data.json
   ```

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
    "name": "200X The Cash (New)",
    "gameNumber": 2613,
    "price": 20,
    "prize": 1000000,
    "total": 4,
    "remain": 4,
    "asOf": "2026-07-16",
    "odds": 3.41,
    "oddsAsOf": "2026-07-16"
  }
]
```

- `price`, `prize`, `total`, `remain`, `asOf` come from Texas Lottery's own daily CSV --
  authoritative, refreshed every run.
- `odds` (overall odds of winning any prize, "1 in X") isn't in that CSV -- it's scraped
  from [ScratchSmarter](https://scratchsmarter.com/texas/scratch-games/)'s public table,
  a third-party site, not an official Texas Lottery source. `oddsAsOf` is *their*
  last-scraped date for that specific game, which can lag behind `asOf` since they don't
  refresh every game daily. Treat `odds` as "likely accurate" rather than guaranteed, and
  cross-check anything important against the ticket itself or texaslottery.com.
- Games are matched between sources by `gameNumber`, not name -- Texas Lottery reuses
  names across different games release years apart, so name-matching alone is unreliable.

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
