# my-hacker-news

Automated twice-daily Hacker News-style page that publishes:

- Top 10 trending GitHub repositories (all languages)
- Trending GitHub repositories discovered from Reddit discussions
- AI / LLM / model training / AI research news from selected subreddits

## How it works

A GitHub Actions workflow runs on a schedule and:

1. Executes `scripts/build_hacker_news.py`
2. Updates `index.html` with the latest crawl
3. Archives the previous page to `archive/index-YYYYMMDD-HHMMSS.html`
4. Writes structured data to `data/latest.json`
5. Commits changes back to the repository
6. Deploys the generated site to GitHub Pages

## Schedule

The workflow is currently configured at:

- `0 13 * * *`
- `0 1 * * *`

These correspond to **06:00 and 18:00 in America/Tijuana while on PDT (UTC-7)**.

> GitHub Actions cron uses UTC and does not auto-adjust DST. If timezone offset changes, update cron lines in `.github/workflows/update.yml`.

## Data sources

- GitHub API Search (`/search/repositories`)
- GitHub Repository API (`/repos/{owner}/{repo}`)
- Reddit API (OAuth) for:
  - `r/MachineLearning`
  - `r/LocalLLaMA`
  - `r/artificial`
  - `r/singularity`

## Reddit scraping in GitHub Actions

Reddit blocks many unauthenticated requests from CI runners. The workflow supports the official Reddit API via OAuth client credentials.

Add these repository secrets:

- `REDDIT_CLIENT_ID`
- `REDDIT_CLIENT_SECRET`

If these are missing, the script falls back to unauthenticated Reddit JSON and may produce warnings or empty Reddit sections.

## Notes

- `GITHUB_TOKEN` is used automatically in GitHub Actions for authenticated API requests.
- Reddit content is filtered for AI/LLM/research keywords for the news section.
- Repository summaries are generated from repository descriptions and include language + stars when available.
