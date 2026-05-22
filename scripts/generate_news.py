"""
Fetch live market news from RSS feeds, pick the 8 most market-moving via Groq,
fetch a relevant Unsplash photo for each story, then write:
  - news.html            full Market Pulse page
  - index.html           4-card preview injected between JDX_NEWS markers

Requires:
  GROQ_API_KEY      (already used by generate_briefing.py)
  UNSPLASH_ACCESS_KEY  (free at unsplash.com/developers — 50 req/hr)
  If UNSPLASH_ACCESS_KEY is absent, category gradient fallback is used.
"""

import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

NEWS_START = "<!-- JDX_NEWS_START -->"
NEWS_END   = "<!-- JDX_NEWS_END -->"

# ---------------------------------------------------------------------------
# Unsplash photo fetching
# ---------------------------------------------------------------------------

# Category → search query for Unsplash
UNSPLASH_QUERIES = {
    "Tech":        "technology semiconductor chip",
    "Energy":      "oil energy refinery pipeline",
    "Fed":         "federal reserve central bank",
    "Macro":       "stock market trading floor",
    "Earnings":    "business finance earnings",
    "Consumer":    "retail shopping consumer",
    "Healthcare":  "medicine pharmaceutical hospital",
    "Geopolitics": "world politics government capitol",
    "Financials":  "wall street bank finance",
}


def fetch_unsplash(category: str, access_key: str) -> str:
    """Return an Unsplash image URL for the given category, or '' on failure."""
    query = UNSPLASH_QUERIES.get(category, "finance economy")
    url   = (
        "https://api.unsplash.com/photos/random"
        f"?query={urllib.parse.quote(query)}"
        "&orientation=landscape"
        f"&client_id={access_key}"
    )
    try:
        req = urllib.request.Request(url, headers={"Accept-Version": "v1"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
        return data["urls"].get("regular", "")
    except Exception as e:
        print(f"  Unsplash warning ({category}): {e}", flush=True)
        return ""


# ---------------------------------------------------------------------------
# RSS fetching
# ---------------------------------------------------------------------------

RSS_FEEDS = [
    ("Reuters",       "https://feeds.reuters.com/reuters/businessNews"),
    ("CNBC",          "https://www.cnbc.com/id/10001147/device/rss/rss.html"),
    ("MarketWatch",   "https://feeds.content.dowjones.io/public/rss/mw_realtimeheadlines"),
    ("Yahoo Finance", "https://finance.yahoo.com/rss/topstories"),
]

_NS = {
    "media":   "http://search.yahoo.com/mrss/",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "atom":    "http://www.w3.org/2005/Atom",
}


def _text(el, tag: str) -> str:
    child = el.find(tag)
    return (child.text or "").strip() if child is not None else ""


def fetch_rss(url: str, source: str, limit: int = 8) -> list[dict]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "JDX-NewsBot/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
        root  = ET.fromstring(raw)
        items = root.findall(".//item") or root.findall(".//atom:entry", _NS)
        results = []
        for item in items[:limit]:
            title = _text(item, "title") or _text(item, "atom:title")
            desc  = _text(item, "description") or _text(item, "atom:summary")
            link  = _text(item, "link") or _text(item, "atom:id")
            desc  = re.sub(r"<[^>]+>", "", desc).strip()[:300]
            if title:
                results.append({"source": source, "headline": title, "desc": desc, "url": link})
        return results
    except Exception as e:
        print(f"  Warning: {source} RSS failed: {e}", flush=True)
        return []


def collect_headlines() -> list[dict]:
    all_items = []
    for source, url in RSS_FEEDS:
        items = fetch_rss(url, source)
        print(f"  {source}: {len(items)} headlines", flush=True)
        all_items.extend(items)
    return all_items[:30]


# ---------------------------------------------------------------------------
# Groq analysis
# ---------------------------------------------------------------------------

NEWS_SYSTEM = """\
You are a senior financial news analyst for JDX, a US market briefing service.
Review the headlines and select the 8 most significant for US equity prices.
For each write a crisp 2-sentence market-impact summary and classify the effect.

Return ONLY valid JSON — no commentary, no markdown. Schema:
{
  "items": [
    {
      "headline":  "original or lightly cleaned headline",
      "summary":   "2-sentence market-impact analysis",
      "sentiment": "bullish" | "bearish",
      "tickers":   ["AAPL", "XLK"],
      "category":  "Macro" | "Fed" | "Earnings" | "Tech" | "Energy" | "Geopolitics" | "Consumer" | "Healthcare" | "Financials",
      "source":    "Reuters",
      "url":       "https://..."
    }
  ]
}
"""


def analyse_with_groq(client, headlines: list[dict]) -> list[dict]:
    lines = []
    for i, h in enumerate(headlines, 1):
        lines.append(f"{i}. [{h['source']}] {h['headline']}")
        if h["desc"]:
            lines.append(f"   {h['desc']}")
        lines.append(f"   URL: {h['url']}")

    print("  Calling Groq for news analysis…", flush=True)
    resp = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": NEWS_SYSTEM},
            {"role": "user",   "content": f"Headlines:\n\n{chr(10).join(lines)}\n\nReturn the JSON now."},
        ],
        max_tokens=3000,
        temperature=0.2,
        response_format={"type": "json_object"},
    )
    data = json.loads(resp.choices[0].message.content.strip())
    return data.get("items", [])


# ---------------------------------------------------------------------------
# HTML builders
# ---------------------------------------------------------------------------

_CATEGORY_CLASS = {
    "Tech":        "news-visual-tech",
    "Energy":      "news-visual-energy",
    "Fed":         "news-visual-fed",
    "Macro":       "news-visual-fed",
    "Earnings":    "news-visual-earnings",
    "Consumer":    "news-visual-consumer",
    "Healthcare":  "news-visual-health",
    "Geopolitics": "news-visual-geo",
    "Financials":  "news-visual-fin",
}


def _sentiment_label(s: str) -> str:
    return "▲ BULLISH" if s == "bullish" else "▼ BEARISH"


def _card_html(item: dict) -> str:
    import html as h

    sentiment = item.get("sentiment", "bullish")
    category  = item.get("category", "Macro")
    headline  = item.get("headline", "")
    summary   = item.get("summary", "")
    tickers   = item.get("tickers", [])
    source    = item.get("source", "")
    url       = item.get("url", "#")
    image_url = item.get("image_url", "")

    vis_class = _CATEGORY_CLASS.get(category, "news-visual-fed")

    if image_url:
        img_tag = f'<img src="{h.escape(image_url)}" alt="" loading="lazy" onerror="this.remove()">'
    else:
        img_tag = ""

    visual = (
        f'<div class="news-card-visual {vis_class}">\n'
        f'      {img_tag}\n'
        f'      <div class="news-card-visual-overlay">'
        f'<span class="news-visual-cat">{h.escape(category.upper())}</span></div>\n'
        f'    </div>'
    )

    chips = "".join(f'<span class="news-ticker-chip">{t}</span>' for t in tickers[:5])
    tickers_html = f'<div class="news-tickers">{chips}</div>' if chips else ""

    return (
        f'<a class="news-card {sentiment}" href="{h.escape(url)}" target="_blank" rel="noopener">\n'
        f'    {visual}\n'
        f'    <div class="news-card-body">\n'
        f'      <div class="news-card-top">'
        f'<span class="news-sentiment {sentiment}">{_sentiment_label(sentiment)}</span></div>\n'
        f'      <h3>{h.escape(headline)}</h3>\n'
        f'      <p>{h.escape(summary)}</p>\n'
        f'      {tickers_html}\n'
        f'      <div class="news-source">{h.escape(source)}</div>\n'
        f'    </div>\n'
        f'  </a>'
    )


def build_news_page(items: list[dict], date_str: str) -> str:
    d       = datetime.strptime(date_str, "%Y-%m-%d")
    display = f"{d.day} {d.strftime('%B')} {d.year}"
    cards   = "\n  ".join(_card_html(item) for item in items)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Market Pulse — JDX · {display}</title>
<link rel="stylesheet" href="assets/styles.css">
</head>
<body>

<header class="site-header">
  <div class="container">
    <a href="index.html" class="wordmark">JDX <span class="accent">DAILY US MARKETS</span></a>
    <nav class="site-nav">
      <a href="index.html">Today</a>
      <a href="news.html" class="active">News</a>
      <a href="archive.html">Archive</a>
      <a href="about.html">About</a>
    </nav>
  </div>
</header>

<section class="news-hero">
  <div class="container">
    <div class="eyebrow">{display} · 09:00 HKT</div>
    <h1>Market Pulse</h1>
    <p>The 8 most market-moving stories today, impact-rated and filtered for US equities.</p>
  </div>
</section>

<section class="container news-page-grid">
  <div class="news-grid full">
  {cards}
  </div>
</section>

<footer class="site-footer">
  <div class="container">
    <div>© 2026 JDX</div>
    <div class="disclaimer">Editorial and informational only. Not investment advice. Always verify figures and consult a licensed advisor before trading.</div>
  </div>
</footer>

</body>
</html>
"""


def build_preview_section(items: list[dict]) -> str:
    cards = "\n    ".join(_card_html(item) for item in items[:4])
    return (
        f"\n{NEWS_START}\n"
        f'<section class="container news-section">\n'
        f'  <div class="news-section-header">\n'
        f'    <h2>Market Pulse</h2>\n'
        f'    <a href="news.html">All stories →</a>\n'
        f'  </div>\n'
        f'  <div class="news-grid">\n'
        f'    {cards}\n'
        f'  </div>\n'
        f'</section>\n'
        f"{NEWS_END}"
    )


# ---------------------------------------------------------------------------
# index.html injection (idempotent — replaces between markers every run)
# ---------------------------------------------------------------------------

def inject_into_index(preview_html: str) -> None:
    index_path = ROOT / "index.html"
    content    = index_path.read_text(encoding="utf-8")

    if NEWS_START in content and NEWS_END in content:
        # Replace everything between (and including) the markers
        pattern = re.escape(NEWS_START) + r".*?" + re.escape(NEWS_END)
        updated = re.sub(pattern, preview_html, content, flags=re.DOTALL)
    else:
        # Fallback: insert before </body>
        updated = content.replace("</body>", preview_html + "\n</body>", 1)

    index_path.write_text(updated, encoding="utf-8")
    print("  Updated index.html news section", flush=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    api_key       = os.environ.get("GROQ_API_KEY")
    unsplash_key  = os.environ.get("UNSPLASH_ACCESS_KEY", "")

    if not api_key:
        print("ERROR: GROQ_API_KEY not set.", file=sys.stderr)
        sys.exit(1)
    try:
        from groq import Groq
    except ImportError:
        print("ERROR: groq not installed.", file=sys.stderr)
        sys.exit(1)

    if unsplash_key:
        print("  Unsplash API key found — will fetch real photos", flush=True)
    else:
        print("  No UNSPLASH_ACCESS_KEY — using category gradients as fallback", flush=True)

    client   = Groq(api_key=api_key)
    now_hkt  = datetime.now(timezone.utc) + timedelta(hours=8)
    date_str = now_hkt.strftime("%Y-%m-%d")

    print("\nFetching RSS headlines…", flush=True)
    headlines = collect_headlines()
    if not headlines:
        print("No headlines fetched — skipping.", flush=True)
        return

    items = analyse_with_groq(client, headlines)
    if not items:
        print("Groq returned no items — skipping.", flush=True)
        return

    # Fetch one Unsplash photo per story
    if unsplash_key:
        print(f"\nFetching Unsplash photos for {len(items)} stories…", flush=True)
        for item in items:
            item["image_url"] = fetch_unsplash(item.get("category", "Macro"), unsplash_key)
            time.sleep(0.3)  # stay well within rate limits
    else:
        for item in items:
            item["image_url"] = ""

    with_img = sum(1 for i in items if i.get("image_url"))
    print(f"  {len(items)} stories ready ({with_img} with photos)", flush=True)

    (ROOT / "news.html").write_text(build_news_page(items, date_str), encoding="utf-8")
    print("  Wrote news.html", flush=True)

    inject_into_index(build_preview_section(items))
    print("Done.", flush=True)


if __name__ == "__main__":
    main()
