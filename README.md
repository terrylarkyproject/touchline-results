# Touchline Results

A football results page and script writer that updates itself. It runs for free on GitHub.

- **`scripts/update.py`** gets finished matches, tables and fixtures from ESPN's public football feed.
- **`.github/workflows/update.yml`** runs that script every 3 hours on GitHub Actions.
- **`index.html`** is the Touchline Script Desk. GitHub Pages hosts it. It writes scripts with your own Claude API key, which stays in your browser.

Leagues: Premier League, La Liga, Serie A, Bundesliga, Ligue 1, Champions League, MLS, World Cup.

## How the data is stored

- `data/results.json` holds the last 14 days in full, plus the tables, fixtures and a list of archive months. The page reloads this small file every 10 minutes.
- `data/archive/YYYY-MM.json` holds older matches, one file per month. The page loads them once per visit.
- The updater moves matches into the archive by itself. Nothing to do by hand.

## One-time setup (about 10 minutes)

1. **Create the repository** `touchline-results` on github.com (Pages is free on public repos).
2. **Upload the files**, including the `.github` folder. If the folder doesn't upload, use **Add file → Create new file**, type `.github/workflows/update.yml` and paste the contents.
3. **Settings → Actions → General → Workflow permissions:** choose **Read and write permissions** and save.
4. **Settings → Pages:** Deploy from a branch, branch **main**, folder **/ (root)**.
5. **First full fill:** Actions → Update results → Run workflow, and type `2026-08-01`. After that it runs every 3 hours.

## Checking it's working

- The **Actions** tab shows a green tick or a red cross for each run, with lines like `Premier League: 10 events`.
- GitHub emails you when a scheduled run fails.
- GitHub pauses scheduled runs after 60 days with no activity. If that happens, click **Enable workflow**.

## Using the Script Desk

Pick a match (or a weekend round-up), and the facts fill in by themselves. In a round-up, each match has a **Short** tick box, so you choose which games get a Short. Press Write the script, record each section, then send the video pack to Match Studio.

## Notes

- ESPN's feed is public but unofficial. If it changes, every league fails and GitHub emails you.
- Saved data is never invented: a field the feed doesn't give is left out.
- To add a league, add a line to `LEAGUES` at the top of `scripts/update.py`.
- The site is public. It holds no secrets; your API key never leaves your browser.
