#!/usr/bin/env python3
"""Build a static Hacker News-style page for trending GitHub repos + Reddit AI news."""

from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = ROOT / "index.html"
ARCHIVE_DIR = ROOT / "archive"
DATA_DIR = ROOT / "data"
DATA_PATH = DATA_DIR / "latest.json"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)
GITHUB_API = "https://api.github.com"

SUBREDDITS = [
    "MachineLearning",
    "LocalLLaMA",
    "artificial",
    "singularity",
]

AI_KEYWORDS = [
    "ai",
    "artificial intelligence",
    "llm",
    "language model",
    "model training",
    "fine-tuning",
    "openai",
    "anthropic",
    "gemini",
    "mistral",
    "deepmind",
    "research",
]


def fetch_json(url: str, headers: Optional[Dict[str, str]] = None) -> Any:
    req_headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        req_headers.update(headers)

    req = urllib.request.Request(url, headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} for {url}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Network error for {url}: {e}") from e


def github_headers() -> Dict[str, str]:
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


def concise_summary(text: str, max_len: int = 180) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    if not text:
        return "No summary available."
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


def github_trending_repos(top_n: int = 10) -> List[Dict[str, Any]]:
    since = (dt.datetime.utcnow() - dt.timedelta(days=7)).strftime("%Y-%m-%d")
    query = urllib.parse.quote(f"created:>={since} stars:>50")
    url = (
        f"{GITHUB_API}/search/repositories"
        f"?q={query}&sort=stars&order=desc&per_page={top_n}"
    )
    data = fetch_json(url, headers=github_headers())
    repos = []
    for item in data.get("items", [])[:top_n]:
        repos.append(
            {
                "name": item.get("full_name"),
                "url": item.get("html_url"),
                "description": concise_summary(item.get("description", "")),
                "language": item.get("language") or "Unknown",
                "stars": item.get("stargazers_count", 0),
                "source": "GitHub Trending",
            }
        )
    return repos


def extract_repo_slug(url: str) -> Optional[str]:
    if not url:
        return None
    m = re.search(r"github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)", url)
    if not m:
        return None
    slug = m.group(1)
    slug = re.sub(r"\.git$", "", slug)
    slug = slug.strip("/")
    return slug


def fetch_repo_details(slug: str) -> Optional[Dict[str, Any]]:
    url = f"{GITHUB_API}/repos/{slug}"
    try:
        data = fetch_json(url, headers=github_headers())
    except Exception:
        return None
    return {
        "name": data.get("full_name", slug),
        "url": data.get("html_url", f"https://github.com/{slug}"),
        "description": concise_summary(data.get("description", "")),
        "language": data.get("language") or "Unknown",
        "stars": data.get("stargazers_count", 0),
        "source": "Reddit",
    }


def reddit_posts(subreddit: str, listing: str = "hot", limit: int = 25) -> List[Dict[str, Any]]:
    url = f"https://www.reddit.com/r/{subreddit}/{listing}.json?limit={limit}"
    cmd = [
        "curl",
        "-sS",
        "-A",
        USER_AGENT,
        "-H",
        "Accept: application/json",
        url,
    ]
    proc = subprocess.run(cmd, check=True, capture_output=True, text=True)
    data = json.loads(proc.stdout)
    children = data.get("data", {}).get("children", [])
    out = []
    for c in children:
        d = c.get("data", {})
        out.append(
            {
                "subreddit": subreddit,
                "title": d.get("title", ""),
                "url": d.get("url", ""),
                "permalink": f"https://www.reddit.com{d.get('permalink', '')}",
                "score": d.get("score", 0),
                "comments": d.get("num_comments", 0),
                "selftext": d.get("selftext", ""),
                "created_utc": d.get("created_utc", 0),
            }
        )
    return out


def looks_like_ai_news(post: Dict[str, Any]) -> bool:
    hay = f"{post.get('title', '')} {post.get('selftext', '')}".lower()
    return any(k in hay for k in AI_KEYWORDS)


def collect_reddit_content() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    repo_map: Dict[str, Dict[str, Any]] = {}
    news_items: List[Dict[str, Any]] = []

    for sr in SUBREDDITS:
        posts = reddit_posts(sr, listing="hot", limit=35)
        for post in posts:
            slug = extract_repo_slug(post.get("url", ""))
            if slug:
                if slug not in repo_map:
                    details = fetch_repo_details(slug)
                    if details:
                        details["reddit_context"] = {
                            "subreddit": post["subreddit"],
                            "post": post["permalink"],
                            "score": post["score"],
                            "comments": post["comments"],
                        }
                        repo_map[slug] = details
                continue

            if looks_like_ai_news(post):
                news_items.append(
                    {
                        "title": post["title"],
                        "url": post["url"] or post["permalink"],
                        "reddit_post": post["permalink"],
                        "subreddit": post["subreddit"],
                        "score": post["score"],
                        "summary": concise_summary(post.get("selftext") or post.get("title")),
                    }
                )

    reddit_repos = sorted(
        repo_map.values(),
        key=lambda r: (
            r.get("reddit_context", {}).get("score", 0),
            r.get("stars", 0),
        ),
        reverse=True,
    )[:10]

    news_items = sorted(news_items, key=lambda n: n.get("score", 0), reverse=True)[:20]
    return reddit_repos, news_items


def archive_previous_index(now: dt.datetime) -> Optional[Path]:
    if not INDEX_PATH.exists():
        return None
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = now.strftime("%Y%m%d-%H%M%S")
    dest = ARCHIVE_DIR / f"index-{stamp}.html"
    shutil.copy2(INDEX_PATH, dest)
    return dest


def render_repo_row(repo: Dict[str, Any]) -> str:
    ctx = repo.get("reddit_context") or {}
    reddit_note = ""
    if ctx:
        reddit_note = (
            f"<div class='meta'>from r/{html.escape(ctx.get('subreddit', ''))} · "
            f"score {ctx.get('score', 0)} · "
            f"<a href='{html.escape(ctx.get('post', '#'))}'>discussion</a></div>"
        )

    return f"""
    <article class=\"card\">
      <h3><a href=\"{html.escape(repo.get('url', '#'))}\" target=\"_blank\" rel=\"noopener\">{html.escape(repo.get('name', 'Unknown repo'))}</a></h3>
      <div class=\"meta\">{html.escape(repo.get('language', 'Unknown'))} · ⭐ {repo.get('stars', 0):,} · {html.escape(repo.get('source', 'Unknown'))}</div>
      <p>{html.escape(repo.get('description', 'No description available.'))}</p>
      {reddit_note}
    </article>
    """


def render_news_row(item: Dict[str, Any]) -> str:
    return f"""
    <article class=\"card\">
      <h3><a href=\"{html.escape(item.get('url', '#'))}\" target=\"_blank\" rel=\"noopener\">{html.escape(item.get('title', 'Untitled'))}</a></h3>
      <div class=\"meta\">r/{html.escape(item.get('subreddit', 'unknown'))} · score {item.get('score', 0)} · <a href=\"{html.escape(item.get('reddit_post', '#'))}\">reddit thread</a></div>
      <p>{html.escape(item.get('summary', 'No summary available.'))}</p>
    </article>
    """


def write_html(
    generated_at_utc: dt.datetime,
    gh_repos: List[Dict[str, Any]],
    reddit_repos: List[Dict[str, Any]],
    news: List[Dict[str, Any]],
    archived_path: Optional[Path],
) -> None:
    generated_str = generated_at_utc.strftime("%Y-%m-%d %H:%M:%S UTC")
    archive_note = ""
    if archived_path:
        archive_note = f"Previous index archived as <code>{html.escape(str(archived_path.relative_to(ROOT)))}</code>."

    gh_html = "\n".join(render_repo_row(r) for r in gh_repos) or "<p>No GitHub repos found.</p>"
    rr_html = "\n".join(render_repo_row(r) for r in reddit_repos) or "<p>No Reddit-linked repos found.</p>"
    news_html = "\n".join(render_news_row(n) for n in news) or "<p>No news found.</p>"

    page = f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>my-hacker-news</title>
  <style>
    :root {{ color-scheme: light dark; }}
    body {{ font-family: Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial; margin: 0; line-height: 1.5; }}
    .wrap {{ max-width: 1024px; margin: 0 auto; padding: 1.2rem; }}
    h1 {{ margin-bottom: .1rem; }}
    .sub {{ opacity: .8; margin: 0 0 1rem 0; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit,minmax(280px,1fr)); gap: 12px; }}
    .card {{ border: 1px solid #8884; border-radius: 10px; padding: 0.75rem 0.9rem; }}
    .meta {{ font-size: .9rem; opacity: .85; }}
    code {{ background: #8883; border-radius: 6px; padding: .1rem .3rem; }}
    a {{ text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
  </style>
</head>
<body>
  <main class=\"wrap\">
    <h1>my-hacker-news</h1>
    <p class=\"sub\">Latest crawl: {generated_str}</p>
    <p>{archive_note}</p>

    <section>
      <h2>Top 10 Trending GitHub Repositories (All Languages)</h2>
      <div class=\"grid\">{gh_html}</div>
    </section>

    <section>
      <h2>Trending Repositories from Reddit</h2>
      <div class=\"grid\">{rr_html}</div>
    </section>

    <section>
      <h2>AI / LLM / AI Research News (Reddit)</h2>
      <div class=\"grid\">{news_html}</div>
    </section>
  </main>
</body>
</html>
"""

    INDEX_PATH.write_text(page, encoding="utf-8")


def write_data_json(
    generated_at_utc: dt.datetime,
    gh_repos: List[Dict[str, Any]],
    reddit_repos: List[Dict[str, Any]],
    news: List[Dict[str, Any]],
) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at_utc": generated_at_utc.isoformat() + "Z",
        "github_trending": gh_repos,
        "reddit_repositories": reddit_repos,
        "ai_news": news,
    }
    DATA_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> int:
    now = dt.datetime.utcnow().replace(microsecond=0)

    archived = archive_previous_index(now)
    gh_repos = github_trending_repos(top_n=10)
    reddit_repos, news = collect_reddit_content()

    write_html(now, gh_repos, reddit_repos, news, archived)
    write_data_json(now, gh_repos, reddit_repos, news)

    print("Built index.html and data/latest.json")
    if archived:
        print(f"Archived previous index to {archived.relative_to(ROOT)}")
    print(f"GitHub repos: {len(gh_repos)}, Reddit repos: {len(reddit_repos)}, News: {len(news)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise
