"""
Generate data/stocks.json — the JDX watchlist with a short AI "JDX Take"
for each tracked stock. Read client-side by stocks.html.

The universal stock search on stocks.html uses live TradingView widgets and
needs no data file; this script only powers the curated-watchlist summaries.

Run by GitHub Actions after generate_news.py. Requires GROQ_API_KEY.
yfinance is used for recent price context but is optional — if it is missing
or fails for a ticker, a summary is still written from the name and sector.
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ticker, display name, TradingView symbol, sector
WATCHLIST = [
    ("AAPL",  "Apple",                  "NASDAQ:AAPL",  "Technology"),
    ("MSFT",  "Microsoft",              "NASDAQ:MSFT",  "Technology"),
    ("NVDA",  "NVIDIA",                 "NASDAQ:NVDA",  "Technology"),
    ("GOOGL", "Alphabet",               "NASDAQ:GOOGL", "Communication Services"),
    ("AMZN",  "Amazon",                 "NASDAQ:AMZN",  "Consumer Discretionary"),
    ("META",  "Meta Platforms",         "NASDAQ:META",  "Communication Services"),
    ("TSLA",  "Tesla",                  "NASDAQ:TSLA",  "Consumer Discretionary"),
    ("AVGO",  "Broadcom",               "NASDAQ:AVGO",  "Technology"),
    ("AMD",   "Advanced Micro Devices", "NASDAQ:AMD",   "Technology"),
    ("ORCL",  "Oracle",                 "NYSE:ORCL",    "Technology"),
    ("CRM",   "Salesforce",             "NYSE:CRM",     "Technology"),
    ("JPM",   "JPMorgan Chase",         "NYSE:JPM",     "Financials"),
    ("BAC",   "Bank of America",        "NYSE:BAC",     "Financials"),
    ("V",     "Visa",                   "NYSE:V",       "Financials"),
    ("MA",    "Mastercard",             "NYSE:MA",      "Financials"),
    ("NFLX",  "Netflix",                "NASDAQ:NFLX",  "Communication Services"),
    ("LLY",   "Eli Lilly",              "NYSE:LLY",     "Healthcare"),
    ("UNH",   "UnitedHealth",           "NYSE:UNH",     "Healthcare"),
    ("JNJ",   "Johnson & Johnson",      "NYSE:JNJ",     "Healthcare"),
    ("WMT",   "Walmart",                "NYSE:WMT",     "Consumer Staples"),
    ("COST",  "Costco",                 "NASDAQ:COST",  "Consumer Staples"),
    ("HD",    "Home Depot",             "NYSE:HD",      "Consumer Discretionary"),
    ("XOM",   "Exxon Mobil",            "NYSE:XOM",     "Energy"),
    ("KO",    "Coca-Cola",              "NYSE:KO",      "Consumer Staples"),
    ("DIS",   "Walt Disney",            "NYSE:DIS",     "Communication Services"),
]

BATCH_SIZE = 9  # stocks per Groq call — keeps each request well under the TPM cap


def fetch_price_context(ticker: str, year: int) -> dict:
    """Recent performance for one ticker via yfinance. Returns {} on failure."""
    try:
        import yfinance as yf
    except ImportError:
        return {}
    try:
        closes = yf.Ticker(ticker).history(period="1y")["Close"]
        if len(closes) < 2:
            return {}
        last = float(closes.iloc[-1])

        def pct_ago(n):
            if len(closes) > n:
                old = float(closes.iloc[-1 - n])
                if old:
                    return (last - old) / old * 100
            return None

        hi = float(closes.max())
        lo = float(closes.min())
        ctx = {
            "price":    round(last, 2),
            "chg_1d":   pct_ago(1),
            "chg_1w":   pct_ago(5),
            "chg_1m":   pct_ago(21),
            "chg_ytd":  None,
            "off_high": (last - hi) / hi * 100 if hi else None,
            "from_low": (last - lo) / lo * 100 if lo else None,
        }
        jan = closes[closes.index.year == year]
        if len(jan) > 0:
            base = float(jan.iloc[0])
            if base:
                ctx["chg_ytd"] = (last - base) / base * 100
        return ctx
    except Exception as e:
        print(f"  yfinance warning ({ticker}): {e}", flush=True)
        return {}


STOCK_SYSTEM = """\
You are a senior equity analyst for JDX, a US market briefing service.
For each stock provided, write a concise 2-3 sentence "JDX Take": what the
recent price action shows, where the stock sits in its 52-week range, and the
key thing for an investor to watch next. Be specific and grounded in the data
given. Analytical, neutral tone — this is editorial, not investment advice.

Return ONLY valid JSON, no markdown, no commentary. Schema:
{ "summaries": { "TICKER": "two to three sentence take", ... } }
"""


def _pf(v) -> str:
    return f"{v:+.1f}%" if isinstance(v, (int, float)) else "n/a"


def analyse_batch(client, batch: list) -> dict:
    lines = []
    for tk, name, _tv, sector, ctx in batch:
        lines.append(f"\n{tk} — {name} ({sector})")
        if ctx:
            lines.append(
                f"  Price ${ctx['price']:.2f} | 1D {_pf(ctx.get('chg_1d'))} | "
                f"1W {_pf(ctx.get('chg_1w'))} | 1M {_pf(ctx.get('chg_1m'))} | "
                f"YTD {_pf(ctx.get('chg_ytd'))}"
            )
            lines.append(
                f"  {_pf(ctx.get('off_high'))} vs 52-wk high, "
                f"{_pf(ctx.get('from_low'))} vs 52-wk low"
            )
        else:
            lines.append("  (live price data unavailable — write a brief general take)")

    user_msg = "Stocks:\n" + "\n".join(lines) + "\n\nReturn the JSON now."
    resp = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": STOCK_SYSTEM},
            {"role": "user",   "content": user_msg},
        ],
        max_tokens=2200,
        temperature=0.3,
        response_format={"type": "json_object"},
    )
    data = json.loads(resp.choices[0].message.content.strip())
    return data.get("summaries", {})


def main() -> None:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("ERROR: GROQ_API_KEY not set.", file=sys.stderr)
        sys.exit(1)
    try:
        from groq import Groq
    except ImportError:
        print("ERROR: groq package not installed.", file=sys.stderr)
        sys.exit(1)

    now_hkt  = datetime.now(timezone.utc) + timedelta(hours=8)
    date_str = now_hkt.strftime("%Y-%m-%d")
    disp     = f"{now_hkt.day} {now_hkt.strftime('%B')} {now_hkt.year}"

    data_dir = ROOT / "data"
    out_path = data_dir / "stocks.json"

    # Idempotent: skip only if today's file already has every summary filled.
    if out_path.exists():
        try:
            prev = json.loads(out_path.read_text(encoding="utf-8"))
            done = (
                prev.get("generated") == date_str
                and len(prev.get("stocks", [])) == len(WATCHLIST)
                and all(s.get("summary") for s in prev.get("stocks", []))
            )
            if done:
                print(f"stocks.json already complete for {date_str} — nothing to do.")
                return
        except Exception:
            pass

    client = Groq(api_key=api_key)

    print(f"\nFetching price context for {len(WATCHLIST)} stocks…", flush=True)
    enriched = []
    for tk, name, tv, sector in WATCHLIST:
        ctx = fetch_price_context(tk, now_hkt.year)
        enriched.append((tk, name, tv, sector, ctx))
        print(f"  {tk:<6} {'ok' if ctx else 'no live data'}", flush=True)

    batches = [enriched[i:i + BATCH_SIZE] for i in range(0, len(enriched), BATCH_SIZE)]
    summaries: dict = {}
    for i, batch in enumerate(batches, 1):
        # 65s before each batch — clears the rate-limit window from the
        # previous script (generate_news) and from the previous batch.
        print("\nWaiting 65s for the Groq rate-limit window…", flush=True)
        time.sleep(65)
        print(f"Groq batch {i}/{len(batches)} ({len(batch)} stocks)…", flush=True)
        try:
            summaries.update(analyse_batch(client, batch))
        except Exception as e:
            print(f"  Batch {i} failed: {e}", flush=True)

    stocks = [
        {
            "ticker":    tk,
            "name":      name,
            "tv_symbol": tv,
            "sector":    sector,
            "summary":   summaries.get(tk, "").strip(),
        }
        for tk, name, tv, sector, _ctx in enriched
    ]

    data_dir.mkdir(exist_ok=True)
    payload = {"generated": date_str, "generated_display": disp, "stocks": stocks}
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    n = sum(1 for s in stocks if s["summary"])
    print(f"\nWrote data/stocks.json — {n}/{len(stocks)} summaries filled.", flush=True)


if __name__ == "__main__":
    main()
