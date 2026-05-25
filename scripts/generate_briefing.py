"""
Generate today's three JDX briefing HTML files using Groq (free tier).
Fetches real market data via yfinance, then calls llama-3.3-70b to write
each edition. Saves HTML to briefings/YYYY-MM-DD/ and rewrites index.html.
Run by GitHub Actions at 01:00 UTC (09:00 HKT) before update_site.py.
"""

import html as html_module
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Market data via yfinance
# ---------------------------------------------------------------------------

TICKERS = {
    # Indices
    "S&P 500":     "^GSPC",
    "Nasdaq 100":  "^NDX",
    "Dow Jones":   "^DJI",
    "Russell 2000":"^RUT",
    "VIX":         "^VIX",
    # Rates / macro
    "10Y Yield":   "^TNX",
    "WTI Crude":   "CL=F",
    "Gold":        "GC=F",
    "DXY":         "DX-Y.NYB",
    # Crypto
    "BTC":         "BTC-USD",
    "ETH":         "ETH-USD",
    # Sector ETFs
    "XLF": "XLF", "XLK": "XLK", "XLI": "XLI", "XLE": "XLE",
    "XLY": "XLY", "XLC": "XLC", "XLP": "XLP", "XLV": "XLV",
    "XLU": "XLU", "XLB": "XLB", "XLRE": "XLRE",
    # Large-cap stocks
    "AAPL": "AAPL", "MSFT": "MSFT", "NVDA": "NVDA", "AMZN": "AMZN",
    "META": "META", "GOOGL": "GOOGL", "TSLA": "TSLA", "AVGO": "AVGO",
    "JPM": "JPM", "GS": "GS", "AAPL": "AAPL",
}


def fetch_market_data() -> dict:
    try:
        import yfinance as yf
    except ImportError:
        print("  yfinance not installed — skipping live data", flush=True)
        return {}

    result = {}
    for name, sym in TICKERS.items():
        try:
            hist = yf.Ticker(sym).history(period="5d")
            if len(hist) >= 2:
                prev  = float(hist["Close"].iloc[-2])
                close = float(hist["Close"].iloc[-1])
                pct   = (close - prev) / prev * 100
                result[name] = {
                    "close": close,
                    "change_pct": pct,
                    "date": hist.index[-1].strftime("%Y-%m-%d"),
                }
        except Exception as e:
            print(f"  Warning: {sym}: {e}", flush=True)
    return result


def market_context_text(data: dict) -> str:
    if not data:
        return "Live market data unavailable — use best-estimate figures from training knowledge."

    def row(name):
        if name not in data:
            return ""
        d = data[name]
        sign = "+" if d["change_pct"] >= 0 else ""
        return f"  {name:<16} {d['close']:>12,.2f}   {sign}{d['change_pct']:+.2f}%   [{d['date']}]"

    sections = [
        ("Indices",          ["S&P 500","Nasdaq 100","Dow Jones","Russell 2000","VIX"]),
        ("Rates/Macro",      ["10Y Yield","WTI Crude","Gold","DXY","BTC","ETH"]),
        ("Sector ETFs",      ["XLF","XLK","XLI","XLE","XLY","XLC","XLP","XLV","XLU","XLB","XLRE"]),
        ("Large-cap stocks", ["AAPL","MSFT","NVDA","AMZN","META","GOOGL","TSLA","AVGO","JPM","GS"]),
    ]
    lines = ["MARKET DATA (most recent US session):"]
    for heading, names in sections:
        lines.append(f"\n{heading}:")
        for n in names:
            r = row(n)
            if r:
                lines.append(r)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Edition specs
# ---------------------------------------------------------------------------

EDITIONS = {
    "concise": {
        "label":   "CONCISE EDITION",
        "meta":    "2-3 page read",
        "topics":  "Macro · Geopolitics · Earnings",
        "deck":    "A 5-minute read of yesterday's US session and today's catalysts — "
                   "what to watch before pre-market opens at 21:30 HKT.",
        "sections": (
            "1. TL;DR — 2 short paragraphs covering the essential session read",
            "2. US Session Recap — data table (Index/Asset | Close | Change | Note) covering S&P, Dow, Nasdaq, Russell, VIX, 10Y, WTI",
            "3. Top large-cap movers — brief prose or small table",
            "4. Spotlight — the single biggest earnings or macro event (key metrics table + 2-3 sentences read-through)",
            "5. Macro & Fed — bullet points: current policy rate, yield levels, today's data releases with times in HKT",
            "6. Geopolitics & Global — bullet points on key themes",
            "7. Earnings — What to Watch — table (When | Ticker | What to look for)",
            "8. Stocks Worth Watching — 4-6 bullet points with one-line 'why'",
            "9. What Could Break the Tape — callout bear box + callout bull box",
            "10. Sources — 4-5 links as <a href='...' target='_blank'>Publisher — Title</a>",
        ),
        "toc": [
            ("#tldr",     "TL;DR"),
            ("#recap",    "Session Recap"),
            ("#spotlight","Spotlight"),
            ("#macro",    "Macro &amp; Fed"),
            ("#geo",      "Geopolitics"),
            ("#earnings", "Earnings"),
            ("#watchlist","Stocks to Watch"),
            ("#risks",    "Risks"),
        ],
    },
    "standard": {
        "label":   "STANDARD EDITION",
        "meta":    "10-minute read",
        "topics":  "Macro · Geopolitics · Earnings · Sectors · Watchlist",
        "deck":    "A wider read of yesterday's session — sector rotation, pre-market action, "
                   "watchlist scan, and what to watch into the US open at 21:30 HKT.",
        "sections": (
            "1. TL;DR — 2 paragraphs including below-the-surface observations",
            "2. US Session Recap — full table (Index/Asset | Level | Change | Why it moved)",
            "3. Top large-cap movers table (Ticker | Change | Catalyst)",
            "4. Sector Rotation — table of all 11 sector ETFs (ETF | Day | Read)",
            "5. Spotlight — deeper breakdown of biggest event with metrics table and read-through to related names",
            "6. Pre-Market & Overnight — US futures, Asia close, Europe, crypto",
            "7. Macro & Fed — FOMC recap, yield curve shape, today's data calendar (time HKT | release | consensus | why it matters)",
            "8. Geopolitics & Global — detailed bullet points",
            "9. Earnings — What to Watch — full week table (When HKT | Ticker | Consensus | What to look for)",
            "10. Watchlist Scan — US Large-Caps table (Ticker | Sector | Why now) — 10-12 names",
            "11. What Could Break the Tape — detailed callout boxes with <ul> bullet lists",
            "12. Positioning Notes — 3 structural observations as bullet points",
            "13. Sources — 6-8 links",
        ),
        "toc": [
            ("#tldr",       "TL;DR"),
            ("#recap",      "Session Recap"),
            ("#sectors",    "Sector Rotation"),
            ("#spotlight",  "Spotlight"),
            ("#premarket",  "Pre-Market"),
            ("#macro",      "Macro &amp; Fed"),
            ("#geo",        "Geopolitics"),
            ("#earnings",   "Earnings"),
            ("#watchlist",  "Watchlist Scan"),
            ("#risks",      "Risks"),
            ("#positioning","Positioning"),
        ],
    },
    "in-depth": {
        "label":   "IN-DEPTH EDITION",
        "meta":    "20-minute read",
        "topics":  "All of the above, plus technicals, options, ratings, week-ahead",
        "deck":    "The full picture: macro, technicals, options, analyst moves, "
                   "sector internals, international context, and a full week ahead.",
        "sections": (
            "1. TL;DR & Editorial Take — 3 paragraphs + 3 structural bullet points",
            "2. US Session Recap — comprehensive table (all major indices, VIX, MOVE, WTI, Brent, 10Y, 2Y, DXY, Gold, BTC)",
            "3. Top movers table (Ticker | Name | Change | Catalyst)",
            "4. Sector Internals — all 11 sector ETFs table (Sector | Day | YTD | Read) + breadth note",
            "5. Spotlight / Deep Dive — full metrics table, key call commentary, read-through map table",
            "6. Technical Levels — table (Ticker | Last | Support | Resistance | Note) for SPY, QQQ, IWM, key stock, 10Y, WTI",
            "7. Options & Positioning — 0DTE flow, put/call, VIX term structure, notable single-name flow, cheap hedge ideas",
            "8. Analyst Rating Changes — table (Ticker | Firm | Action | New PT | Note) — 5-7 rows",
            "9. Pre-Market & Overnight — comprehensive: futures, Asia, Europe, FX pairs, commodities, crypto",
            "10. Macro & Fed (Deep) — rate path table (Meeting | Cut Odds | Note) + today's data calendar table",
            "11. Geopolitics & Global (Deep) — scenario trees where relevant",
            "12. Earnings — This Week & Next — two tables",
            "13. Full Watchlist Scan — 12-15 names table (Ticker | Sector | Setup | Risk)",
            "14. What Could Break the Tape — detailed bullish and bearish scenario bullets",
            "15. Positioning & Structural Notes — 5+ observations",
            "16. Sources — 10-12 links",
        ),
        "toc": [
            ("#tldr",       "TL;DR &amp; Take"),
            ("#recap",      "Session Recap"),
            ("#sectors",    "Sector Internals"),
            ("#spotlight",  "Deep Dive"),
            ("#technicals", "Technical Levels"),
            ("#options",    "Options &amp; Positioning"),
            ("#ratings",    "Analyst Changes"),
            ("#premarket",  "Pre-Market"),
            ("#macro",      "Macro &amp; Fed"),
            ("#geo",        "Geopolitics"),
            ("#earnings",   "Earnings — Week"),
            ("#watchlist",  "Watchlist"),
            ("#risks",      "Risks"),
            ("#positioning","Positioning Notes"),
        ],
    },
}

# ---------------------------------------------------------------------------
# LLM generation
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are the editor and writer of JDX, a daily US market briefing published at 09:00 HKT.
Audience: sophisticated, finance-literate investors in Hong Kong and Asia.

TONE: Authoritative, direct, data-driven. No fluff. Active voice. Numbers are precise.
This is editorial and informational — add the disclaimer "Not investment advice" only in the footer (already in the template).

REQUIRED HTML CONVENTIONS:
- Ticker symbols:   <span class="ticker">NVDA</span>
- Numbers/levels:   <span class="num">7,300</span>
- Positive moves:   <span class="up">+1.9%</span>
- Negative moves:   <span class="down">-4.9%</span>
- Data tables:      <table class="data"> with <thead> and <tbody>
- Callout boxes:    <div class="callout bear"> or <div class="callout bull">
                      each must start with <div class="label">BEARISH TRIGGERS</div>
- Sources block:    <div class="sources"><h3>Sources</h3><ul>…</ul></div>
- H2 section tags must carry matching id attributes, e.g. <h2 id="tldr">

Output ONLY the complete HTML document. No commentary. No markdown fences.
Start with <!DOCTYPE html> and end with </html>.
"""


def _toc_html(toc: list) -> str:
    return "\n      ".join(
        f'<a href="{href}">{label}</a>' for href, label in toc
    )


def _display_date(date_str: str) -> str:
    d = datetime.strptime(date_str, "%Y-%m-%d")
    return f"{d.day} {d.strftime('%B').upper()} {d.year}"


def generate_edition(client, date_str: str, edition: str, mkt: str) -> str:
    spec   = EDITIONS[edition]
    disp   = _display_date(date_str)
    eyebrow = (
        f"{spec['label']} <span class=\"dot\">●</span> "
        f"{disp} <span class=\"dot\">●</span> 09:00 HKT"
    )
    sections_text = "\n".join(spec["sections"])
    toc           = _toc_html(spec["toc"])

    user_msg = f"""\
Write the {edition.upper()} edition of the JDX Daily US Market Briefing for {date_str}.

{mkt}

REQUIRED SECTIONS (write all of them, in this order):
{sections_text}

Use this HTML skeleton — fill in every [PLACEHOLDER]:

<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{edition.capitalize()} — JDX Briefing · {disp}</title>
<link rel="stylesheet" href="../../assets/styles.css">
<script>(function(){{var d=document.documentElement;try{{d.setAttribute("data-theme",localStorage.getItem("jdx-theme")||"auto");d.setAttribute("data-size",localStorage.getItem("jdx-size")||"md");}}catch(e){{d.setAttribute("data-theme","auto");d.setAttribute("data-size","md");}}}})();</script>
</head>
<body>

<header class="site-header">
  <div class="container">
    <a href="../../index.html" class="wordmark">JDX <span class="accent">DAILY US MARKETS</span></a>
    <nav class="site-nav">
      <a href="../../index.html" class="active">Today</a>
      <a href="../../news.html">News</a>
      <a href="../../stocks.html">Stocks</a>
      <a href="../../archive.html">Archive</a>
      <a href="../../about.html">About</a>
    </nav>
  </div>
</header>

<main class="container briefing">
  <div class="briefing-header">
    <div class="eyebrow">{eyebrow}</div>
    <h1>[WRITE A SHARP, SPECIFIC HEADLINE BASED ON TODAY'S MARKET DATA — no generic phrasing]</h1>
    <p class="deck">{spec['deck']}</p>
    <div class="briefing-meta">
      <span>{spec['meta']}</span>
      <span>·</span>
      <span>Topics: {spec['topics']}</span>
      <span class="download"><a href="{edition}.pdf" class="btn btn-ghost">Download PDF</a></span>
    </div>
  </div>

  <div class="briefing-body">
    <div class="briefing-content">

[WRITE ALL REQUIRED SECTIONS HERE — each section as <h2 id="..."> ... ]

    </div>

    <aside class="toc">
      <div class="toc-title">CONTENTS</div>
      {toc}
    </aside>
  </div>
</main>

<footer class="site-footer">
  <div class="container">
    <div>© 2026 JDX</div>
    <div class="disclaimer">Editorial and informational only. Not investment advice. Always verify figures and consult a licensed advisor before trading.</div>
  </div>
</footer>

<script src="../../assets/reveal.js" defer></script>
<script src="../../assets/settings.js" defer></script>
</body>
</html>
"""

    print(f"  Calling Groq for {edition}…", flush=True)
    resp = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_msg},
        ],
        max_tokens=8000,
        temperature=0.35,
    )
    content = resp.choices[0].message.content.strip()
    # Strip any accidental markdown fences the model may add
    content = re.sub(r"^```html\s*", "", content, flags=re.IGNORECASE)
    content = re.sub(r"^```\s*",     "", content)
    content = re.sub(r"\s*```$",     "", content)
    return content


# ---------------------------------------------------------------------------
# index.html rebuild
# ---------------------------------------------------------------------------

class _TextParser(HTMLParser):
    def __init__(self): super().__init__(); self._buf = []; self._on = False
    def handle_starttag(self, tag, attrs):
        if tag == "h1": self._on = True
    def handle_endtag(self, tag):
        if tag == "h1": self._on = False
    def handle_data(self, data):
        if self._on: self._buf.append(data)
    def result(self): return "".join(self._buf).strip()


def _extract_h1(html: str) -> str:
    p = _TextParser()
    p.feed(html)
    return p.result()


def _extract_tldr(html: str) -> str:
    """Pull plain text from the first <p> after the TL;DR h2."""
    m = re.search(
        r'<h2[^>]*id=["\']tldr["\'][^>]*>.*?</h2>\s*<p>(.*?)</p>',
        html, re.DOTALL | re.IGNORECASE,
    )
    if not m:
        return ""

    class Strip(HTMLParser):
        def __init__(self): super().__init__(); self._b = []
        def handle_data(self, d): self._b.append(d)
        def result(self): return "".join(self._b).strip()

    p = Strip(); p.feed(m.group(1)); return p.result()


def rebuild_index(date_str: str, standard_html: str) -> None:
    d      = datetime.strptime(date_str, "%Y-%m-%d")
    eyebrow = (
        f"{d.strftime('%A').upper()} · {d.day} {d.strftime('%B').upper()} "
        f"{d.year} · 09:00 HKT"
    )
    headline = html_module.escape(_extract_h1(standard_html))
    lede     = html_module.escape(
        _extract_tldr(standard_html)
        or "Today's US market briefing. Choose your depth below."
    )

    content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>JDX — Daily US Market Briefing</title>
<meta name="description" content="Daily US market briefing — published at 9am HKT every morning, in concise, standard, and in-depth editions.">
<link rel="stylesheet" href="assets/styles.css">
<script>(function(){{var d=document.documentElement;try{{d.setAttribute("data-theme",localStorage.getItem("jdx-theme")||"auto");d.setAttribute("data-size",localStorage.getItem("jdx-size")||"md");}}catch(e){{d.setAttribute("data-theme","auto");d.setAttribute("data-size","md");}}}})();</script>
</head>
<body>

<header class="site-header">
  <div class="container">
    <a href="index.html" class="wordmark">JDX <span class="accent">DAILY US MARKETS</span></a>
    <nav class="site-nav">
      <a href="index.html" class="active">Today</a>
      <a href="news.html">News</a>
      <a href="stocks.html">Stocks</a>
      <a href="archive.html">Archive</a>
      <a href="about.html">About</a>
    </nav>
  </div>
</header>

<section class="hero">
  <div class="container">
    <div class="eyebrow">{eyebrow}</div>
    <h1>{headline}</h1>
    <p class="lede">{lede}</p>
  </div>
</section>

<section class="container versions">
  <div class="version-card">
    <div class="label">EDITION 01</div>
    <h3>Concise</h3>
    <div class="meta">2-3 pages · 5-min read</div>
    <p>The essentials: market recap, top movers, spotlight, macro/Fed, geopolitics, today's earnings, and what could break the tape.</p>
    <div class="actions">
      <a href="briefings/{date_str}/concise.html" class="btn btn-primary">Read</a>
      <a href="briefings/{date_str}/concise.pdf" class="btn btn-ghost">PDF</a>
    </div>
  </div>

  <div class="version-card">
    <div class="label">EDITION 02</div>
    <h3>Standard</h3>
    <div class="meta">4-6 pages · 10-min read</div>
    <p>Everything in Concise plus sector rotation, pre-market futures, a watchlist scan across US large-caps, and positioning notes.</p>
    <div class="actions">
      <a href="briefings/{date_str}/standard.html" class="btn btn-primary">Read</a>
      <a href="briefings/{date_str}/standard.pdf" class="btn btn-ghost">PDF</a>
    </div>
  </div>

  <div class="version-card">
    <div class="label">EDITION 03</div>
    <h3>In-depth</h3>
    <div class="meta">7-10 pages · 20-min read</div>
    <p>Everything in Standard plus technical levels, options positioning, analyst rating changes, the full earnings calendar, and a structural take.</p>
    <div class="actions">
      <a href="briefings/{date_str}/in-depth.html" class="btn btn-primary">Read</a>
      <a href="briefings/{date_str}/in-depth.pdf" class="btn btn-ghost">PDF</a>
    </div>
  </div>
</section>

<section class="container stock-teaser">
  <div class="stock-teaser-inner">
    <div>
      <div class="label">NEW · STOCK LOOKUP</div>
      <h2>Look up any US stock</h2>
      <p>Interactive charts, key stats, technicals and JDX's daily AI take on 25 watchlist names.</p>
    </div>
    <a href="stocks.html" class="btn">Open Stock Lookup →</a>
  </div>
</section>

<!-- JDX_NEWS_START -->
<!-- JDX_NEWS_END -->

<footer class="site-footer">
  <div class="container">
    <div>© 2026 JDX</div>
    <div class="disclaimer">Editorial and informational only. Not investment advice. Always verify figures and consult a licensed advisor before trading.</div>
  </div>
</footer>

<script src="assets/reveal.js" defer></script>
<script src="assets/settings.js" defer></script>
</body>
</html>
"""
    (ROOT / "index.html").write_text(content, encoding="utf-8")
    print(f"  Rebuilt index.html → {date_str}", flush=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("ERROR: GROQ_API_KEY environment variable not set.", file=sys.stderr)
        sys.exit(1)

    try:
        from groq import Groq
    except ImportError:
        print("ERROR: groq package not installed (pip install groq).", file=sys.stderr)
        sys.exit(1)

    client = Groq(api_key=api_key)

    # Date in HKT (UTC+8)
    now_hkt  = datetime.now(timezone.utc) + timedelta(hours=8)
    date_str = now_hkt.strftime("%Y-%m-%d")
    out_dir  = ROOT / "briefings" / date_str

    all_exist = all(
        (out_dir / f"{e}.html").exists()
        for e in ("concise", "standard", "in-depth")
    )
    if all_exist:
        print(f"Briefings for {date_str} already exist — nothing to do.")
        return

    out_dir.mkdir(parents=True, exist_ok=True)

    print("\nFetching live market data…", flush=True)
    mkt_data = fetch_market_data()
    mkt_text = market_context_text(mkt_data)
    print(mkt_text, flush=True)

    print(f"\nGenerating briefings for {date_str}…", flush=True)
    generated: dict[str, str] = {}

    for edition in ("concise", "standard", "in-depth"):
        path = out_dir / f"{edition}.html"
        if path.exists():
            print(f"  {edition} already exists — skipping", flush=True)
            generated[edition] = path.read_text(encoding="utf-8")
            continue

        body = generate_edition(client, date_str, edition, mkt_text)
        path.write_text(body, encoding="utf-8")
        generated[edition] = body
        print(f"  Saved {path.name}  ({len(body):,} chars)", flush=True)

        # Wait 65s between calls — Groq free tier allows 12,000 tokens/min,
        # so each edition must sit in its own minute window.
        if edition != "in-depth":
            print("  Waiting 65s for Groq rate-limit window to reset…", flush=True)
            time.sleep(65)

    headline = _extract_h1(generated["standard"])
    print(f"\nHeadline: {headline}", flush=True)
    rebuild_index(date_str, generated["standard"])
    print("\nDone. Run update_site.py next to generate PDFs and update archive.html.", flush=True)


if __name__ == "__main__":
    main()
