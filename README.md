# my-hacker-news

Automated twice-daily Hacker News-style page that publishes:

- Top 10 trending GitHub repositories (all languages)
- Top 10 repositories for each major language
- Hacker News front-page links with concise summaries

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
- Hacker News Algolia API (`front_page` feed)

## Notes

- `GITHUB_TOKEN` is used automatically in GitHub Actions for authenticated API requests.
- Repository summaries include language + stars when available.
- Previous `index.html` pages are preserved in `archive/` with timestamps.
