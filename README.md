# Touchline Results

A football results page that updates itself, with no Claude needed. It runs for free on GitHub.

- **`scripts/update.py`** gets finished matches from ESPN's public football feed and saves them in `data/results.json`.
- **`.github/workflows/update.yml`** runs that script every 3 hours on GitHub Actions.
- **`index.html`** is the page. GitHub Pages hosts it.

Leagues: Premier League, La Liga, Serie A, Bundesliga, Ligue 1, Champions League, MLS, World Cup.
For each match it saves the score, goal minutes and scorers, penalties and own goals, red cards, substitution minutes, team stats and the players used. Assists are added when the feed's commentary credits one. A match whose stats aren't out yet is marked "Waiting", and the next run tries again.

## One-time setup (about 10 minutes)

1. **Create the repository.** On github.com, click **New repository**, name it `touchline-results`, choose **Public**, and click **Create repository**. (Pages is free on public repos.)
2. **Upload the files.** On the new repo page, click **uploading an existing file**. Drag in everything from this folder, including the `.github` folder, then click **Commit changes**.
   - If the `.github` folder doesn't upload, which some browsers skip because the name starts with a dot: click **Add file → Create new file**, type `.github/workflows/update.yml` as the name, paste in the contents of that file, and commit.
3. **Let the updater save.** Go to **Settings → Actions → General → Workflow permissions**, choose **Read and write permissions**, and click **Save**.
4. **Turn on the website.** Go to **Settings → Pages**. Under *Build and deployment*, set Source to **Deploy from a branch**, Branch to **main**, and folder to **/ (root)**. Click **Save**. About a minute later the address appears at the top: `https://<your-username>.github.io/touchline-results/`.
5. **Do the first full fill.** Go to **Actions → Update results → Run workflow**. Type `2026-08-01` in the box and click **Run workflow**. This fetches the whole season so far and fills in stats for the matches Claude saved with scores only. It takes a few minutes. After that, it runs by itself every 3 hours.

## Checking it's working

- **Actions tab:** each run shows a green tick, or a red cross if something failed. Click a run to see lines like `Premier League: 10 events` and `Done: 4 added, 0 updated`.
- **Failure emails:** GitHub emails you when a scheduled run fails, so you don't have to keep checking.
- **Inactive repos:** GitHub pauses scheduled runs in a repo with no activity for 60 days. The bot's own result commits count as activity during the season. If runs ever stop, open the Actions tab and click **Enable workflow**.

## Using it with the Script Desk

Open a match and click **Copy facts**. Then paste into the "Facts and stats you have" box in the Touchline Script Desk. The script writing itself still happens in Claude, because it needs AI.

## Notes

- ESPN's feed is public and free, but it isn't an official API, so ESPN could change it. If that happens, every league will fail, and you'll get a failure email from GitHub.
- The saved data is never invented. If the feed doesn't give a field, it's left out.
- To add a league, add a line to `LEAGUES` at the top of `scripts/update.py`. For example, `"eng.2": "Championship",`.
