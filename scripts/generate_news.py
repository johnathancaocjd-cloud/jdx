"""
Fetch live market news headlines from free RSS feeds, pass to Groq to pick
the 8 most market-moving stories and rate each bullish/bearish, then write:
  - news.html         (full news page)
  - injects a 4-card preview section into index.html

No extra API key needed beyond GROQ_API_KEY (already used by generate_briefing.py).
Run by GitHub Actions after generate_briefing.py.
"""

import json
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

NEWS_PREVIEW_MARKER = "<!-- NEWS_PREVIEW_PLACEHOLDER -->"

# ---------------------------------------------------------------------------
# RSS fetching
# ---------------------------------------------------------------------------

RSS_FEEDS = [
    ("Reuters",     "https://feeds.reuters.com/reuters/businessNews"),
    ("CNBC",        "https://www.cnbc.com/id/10001147/device/rss/rss.html"),
    ("MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_realtimeheadlines"),
    ("Yahoo Finance","https://finance.yahoo.com/rss/topstories"),
]

def _text(el, tag):
    child = el.find(tag)
    return (child.text or "").strip() if child is not None else ""


def fetch_rss(url: str, source: str, limit: int = 8) -> list[dict]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "JDX-NewsBot/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
        root = ET.fromstring(raw)
        # Handle both RSS <channel><item> and Atom <entry>
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        items = root.findall(".//item") or root.findall(".//atom:entry", ns)
        results = []
        for item in items[:limit]:
            title = _text(item, "title") or _text(item, "atom:title")
            desc  = _text(item, "description") or _text(item, "atom:summary")
            link  = _text(item, "link") or _text(item, "atom:id")
            # Strip HTML tags from description
            desc = re.sub(r"<[^>]+>", "", desc).strip()
            desc = desc[:300]
            if title:
                results.append({"source": source, "headline": title, "desc": desc, "url": link})
        return results
    except Exception as e:
        print(f"  Warning: could not fetch {source} RSS: {e}", flush=True)
        return []


def collect_headlines() -> list[dict]:
    all_items = []
    for source, url in RSS_FEEDS:
        items = fetch_rss(url, source)
        print(f"  {source}: {len(items)} headlines", flush=True)
        all_items.extend(items)
    return all_items[:30]  # cap at 30 to keep prompt manageable


# ---------------------------------------------------------------------------
# Groq analysis
# ---------------------------------------------------------------------------

NEWS_SYSTEM = """\
You are a senior financial news analyst for JDX, a US market briefing service.
Your job: review a list of news headlines and select the 8 most significant for
US equity prices. For each, write a crisp 2-sentence market-impact summary and
classify the likely effect on US stocks.

Return ONLY valid JSON — no commentary, no markdown fences. Schema:
{
  "items": [
    {
      "headline": "original or slightly cleaned headline",
      "summary":  "2-sentence market-impact analysis",
      "sentiment": "bullish" | "bearish",
      "tickers":  ["AAPL", "XLK"],
      "category": "Macro" | "Fed" | "Earnings" | "Tech" | "Energy" | "Geopolitics" | "Consumer" | "Financials",
      "source":   "Reuters",
      "url":      "https://..."
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
    feed_text = "\n".join(lines)

    print("  Calling Groq for news analysis…", flush=True)
    resp = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": NEWS_SYSTEM},
            {"role": "user",   "content": f"Headlines:\n\n{feed_text}\n\nReturn the JSON now."},
        ],
        max_tokens=3000,
        temperature=0.2,
        response_format={"type": "json_object"},
    )
    raw = resp.choices[0].message.content.strip()
    data = json.loads(raw)
    return data.get("items", [])


# ---------------------------------------------------------------------------
# HTML builders
# ---------------------------------------------------------------------------

def _sentiment_label(s: str) -> str:
    return "▲ BULLISH" if s == "bullish" else "▼ BEARISH"


def _card_html(item: dict, link_wrap: bool = True) -> str:
    sentiment = item.get("sentiment", "bullish")
    category  = item.get("category", "Markets")
    headline  = item.get("headline", "")
    summary   = item.get("summary", "")
    tickers   = item.get("tickers", [])
    source    = item.get("source", "")
    url       = item.get("url", "#")

    ticker_chips = "".join(
        f'<span class="news-ticker-chip">{t}</span>' for t in tickers[:6]
    )
    tickers_html = f'<div class="news-tickers">{ticker_chips}</div>' if ticker_chips else ""

    import html as h
    card_inner = f"""
    <div class="news-card-top">
      <span class="news-category">{h.escape(category)}</span>
      <span class="news-sentiment {sentiment}">{_sentiment_label(sentiment)}</span>
    </div>
    <h3>{h.escape(headline)}</h3>
    <p>{h.escape(summary)}</p>
    {tickers_html}
    <div class="news-source">{h.escape(source)}</div>"""

    if link_wrap:
        return f'<a class="news-card {sentiment}" href="{h.escape(url)}" target="_blank" rel="noopener">{card_inner}\n  </a>'
    else:
        return f'<div class="news-card {sentiment}">{card_inner}\n  </div>'


def build_news_page(items: list[dict], date_str: str) -> str:
    d = datetime.strptime(date_str, "%Y-%m-%d")
    display = f"{d.day} {d.strftime('%B')} {d.year}"
    cards_html = "\n  ".join(_card_html(item) for item in items)

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
  {cards_html}
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
    """4-card preview block to inject into index.html."""
    preview_items = items[:4]
    cards_html = "\n    ".join(_card_html(item) for item in preview_items)
    return f"""
<section class="container news-section">
  <div class="news-section-header">
    <h2>Market Pulse</h2>
    <a href="news.html">All stories →</a>
  </div>
  <div class="news-grid">
    {cards_html}
  </div>
</section>
"""


# ---------------------------------------------------------------------------
# index.html injection
# ---------------------------------------------------------------------------

def inject_into_index(preview_html: str) -> None:
    index_path = ROOT / "index.html"
    content = index_path.read_text(encoding="utf-8")

    if NEWS_PREVIEW_MARKER in content:
        updated = content.replace(NEWS_PREVIEW_MARKER, preview_html, 1)
    else:
        # Fallback: insert before </body>
        updated = content.replace("</body>", preview_html + "\n</body>", 1)

    index_path.write_text(updated, encoding="utf-8")
    print("  Injected news preview into index.html", flush=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("ERROR: GROQ_API_KEY not set.", file=sys.stderr)
        sys.exit(1)

    try:
        from groq import Groq
    except ImportError:
        print("ERROR: groq not installed.", file=sys.stderr)
        sys.exit(1)

    client   = Groq(api_key=api_key)
    now_hkt  = datetime.now(timezone.utc) + timedelta(hours=8)
    date_str = now_hkt.strftime("%Y-%m-%d")

    print("\nFetching RSS headlines…", flush=True)
    headlines = collect_headlines()
    if not headlines:
        print("No headlines fetched — skipping news generation.", flush=True)
        return

    items = analyse_with_groq(client, headlines)
    if not items:
        print("Groq returned no items — skipping.", flush=True)
        return

    print(f"  Got {len(items)} rated stories", flush=True)

    # Write news.html
    news_html = build_news_page(items, date_str)
    (ROOT / "news.html").write_text(news_html, encoding="utf-8")
    print("  Wrote news.html", flush=True)

    # Inject preview into index.html
    preview_html = build_preview_section(items)
    inject_into_index(preview_html)

    print("Done.", flush=True)


if __name__ == "__main__":
    main()
