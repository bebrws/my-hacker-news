#!/usr/bin/env python3
"""Build static my-hacker-news page: GitHub trending + top repos by language + Hacker News."""

from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
import shutil
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
HN_ALGOLIA = "https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=30"

TOP_LANGUAGES = [
    "Python",
    "JavaScript",
    "TypeScript",
    "Go",
    "Rust",
    "Java",
    "C++",
    "C#",
    "Swift",
    "Kotlin",
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


def _normalize_repo_item(item: Dict[str, Any], source: str) -> Dict[str, Any]:
    return {
        "name": item.get("full_name"),
        "url": item.get("html_url"),
        "description": concise_summary(item.get("description", "")),
        "language": item.get("language") or "Unknown",
        "stars": item.get("stargazers_count", 0),
        "source": source,
    }


def github_trending_repos(top_n: int = 10) -> List[Dict[str, Any]]:
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=7)).strftime("%Y-%m-%d")
    query = urllib.parse.quote(f"created:>={since} stars:>50")
    url = (
        f"{GITHUB_API}/search/repositories"
        f"?q={query}&sort=stars&order=desc&per_page={top_n}"
    )
    data = fetch_json(url, headers=github_headers())
    return [_normalize_repo_item(item, "GitHub Trending") for item in data.get("items", [])[:top_n]]


def github_top_by_language(language: str, top_n: int = 10) -> List[Dict[str, Any]]:
    query = urllib.parse.quote(f"language:{language} stars:>500")
    url = (
        f"{GITHUB_API}/search/repositories"
        f"?q={query}&sort=stars&order=desc&per_page={top_n}"
    )
    data = fetch_json(url, headers=github_headers())
    return [_normalize_repo_item(item, f"GitHub Top ({language})") for item in data.get("items", [])[:top_n]]


def github_top_repos_per_language(top_n: int = 10) -> Tuple[Dict[str, List[Dict[str, Any]]], List[str]]:
    out: Dict[str, List[Dict[str, Any]]] = {}
    warnings: List[str] = []
    for lang in TOP_LANGUAGES:
        try:
            out[lang] = github_top_by_language(lang, top_n=top_n)
        except Exception as e:
            warnings.append(f"Failed GitHub language query ({lang}): {e}")
            out[lang] = []
    return out, warnings


def hacker_news_items(limit: int = 20) -> List[Dict[str, Any]]:
    data = fetch_json(HN_ALGOLIA)
    hits = data.get("hits", [])
    out: List[Dict[str, Any]] = []

    for h in hits[:limit]:
        item_id = h.get("objectID", "")
        hn_link = f"https://news.ycombinator.com/item?id={item_id}" if item_id else "https://news.ycombinator.com/"
        external = h.get("url") or hn_link
        points = h.get("points", 0) or 0
        comments = h.get("num_comments", 0) or 0
        author = h.get("author", "unknown")

        summary_seed = h.get("story_text") or h.get("comment_text") or (
            f"Popular Hacker News discussion with {points} points and {comments} comments by {author}."
        )

        out.append(
            {
                "title": h.get("title") or h.get("story_title") or "Untitled",
                "url": external,
                "hn_link": hn_link,
                "points": points,
                "comments": comments,
                "author": author,
                "summary": concise_summary(summary_seed),
            }
        )

    return out


def archive_previous_index(now: dt.datetime) -> Optional[Path]:
    if not INDEX_PATH.exists():
        return None
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = now.strftime("%Y%m%d-%H%M%S")
    dest = ARCHIVE_DIR / f"index-{stamp}.html"
    shutil.copy2(INDEX_PATH, dest)
    return dest


def render_repo_row(repo: Dict[str, Any]) -> str:
    return f"""
    <article class=\"card\">
      <h3><a href=\"{html.escape(repo.get('url', '#'))}\" target=\"_blank\" rel=\"noopener\">{html.escape(repo.get('name', 'Unknown repo'))}</a></h3>
      <div class=\"meta\">{html.escape(repo.get('language', 'Unknown'))} · ⭐ {repo.get('stars', 0):,} · {html.escape(repo.get('source', 'Unknown'))}</div>
      <p>{html.escape(repo.get('description', 'No description available.'))}</p>
    </article>
    """


def render_hn_row(item: Dict[str, Any]) -> str:
    return f"""
    <article class=\"card\">
      <h3><a href=\"{html.escape(item.get('url', '#'))}\" target=\"_blank\" rel=\"noopener\">{html.escape(item.get('title', 'Untitled'))}</a></h3>
      <div class=\"meta\">{item.get('points', 0)} points · {item.get('comments', 0)} comments · by {html.escape(item.get('author', 'unknown'))} · <a href=\"{html.escape(item.get('hn_link', '#'))}\">HN thread</a></div>
      <p>{html.escape(item.get('summary', 'No summary available.'))}</p>
    </article>
    """


def write_html(
    generated_at_utc: dt.datetime,
    gh_repos: List[Dict[str, Any]],
    top_by_language: Dict[str, List[Dict[str, Any]]],
    hn_items: List[Dict[str, Any]],
    archived_path: Optional[Path],
    warnings: List[str],
) -> None:
    generated_str = generated_at_utc.strftime("%Y-%m-%d %H:%M:%S UTC")
    archive_note = ""
    if archived_path:
        archive_note = f"Previous index archived as <code>{html.escape(str(archived_path.relative_to(ROOT)))}</code>."

    gh_html = "\n".join(render_repo_row(r) for r in gh_repos) or "<p>No GitHub repos found.</p>"

    lang_sections = []
    for lang, repos in top_by_language.items():
        lang_html = "\n".join(render_repo_row(r) for r in repos) or "<p>No repos found for this language.</p>"
        lang_sections.append(
            f"<details><summary><strong>{html.escape(lang)}</strong> — Top 10</summary><div class='grid'>{lang_html}</div></details>"
        )
    top_lang_html = "\n".join(lang_sections)

    hn_html = "\n".join(render_hn_row(n) for n in hn_items) or "<p>No Hacker News items found.</p>"

    warnings_html = ""
    if warnings:
        items = "".join(f"<li>{html.escape(w)}</li>" for w in warnings)
        warnings_html = f"<section><h2>Crawler Warnings</h2><ul>{items}</ul></section>"

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
    details {{ margin: .5rem 0; border: 1px solid #8884; border-radius: 8px; padding: .5rem; }}
    summary {{ cursor: pointer; }}
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
      <h2>Top 10 Repositories by Language</h2>
      {top_lang_html}
    </section>

    <section>
      <h2>Hacker News (Front Page)</h2>
      <div class=\"grid\">{hn_html}</div>
    </section>

    {warnings_html}
  </main>
</body>
</html>
"""

    INDEX_PATH.write_text(page, encoding="utf-8")


def write_data_json(
    generated_at_utc: dt.datetime,
    gh_repos: List[Dict[str, Any]],
    top_by_language: Dict[str, List[Dict[str, Any]]],
    hn_items: List[Dict[str, Any]],
    warnings: List[str],
) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at_utc": generated_at_utc.isoformat().replace("+00:00", "Z"),
        "github_trending": gh_repos,
        "github_top_by_language": top_by_language,
        "hacker_news": hn_items,
        "warnings": warnings,
    }
    DATA_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> int:
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)

    archived = archive_previous_index(now)
    gh_repos = github_trending_repos(top_n=10)
    top_by_language, warnings = github_top_repos_per_language(top_n=10)

    try:
        hn_items = hacker_news_items(limit=20)
    except Exception as e:
        warnings.append(f"Failed to fetch Hacker News: {e}")
        hn_items = []

    write_html(now, gh_repos, top_by_language, hn_items, archived, warnings)
    write_data_json(now, gh_repos, top_by_language, hn_items, warnings)

    print("Built index.html and data/latest.json")
    if archived:
        print(f"Archived previous index to {archived.relative_to(ROOT)}")
    print(
        f"GitHub repos: {len(gh_repos)}, "
        f"language groups: {len(top_by_language)}, "
        f"Hacker News items: {len(hn_items)}"
    )
    if warnings:
        print(f"Warnings: {len(warnings)}")
        for w in warnings:
            print(f" - {w}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise
