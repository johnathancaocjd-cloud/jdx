"""
Run by GitHub Actions on every push to main.
  1. Generates missing PDFs for any briefing date (requires weasyprint).
  2. Inserts a new entry into archive.html for any date not already listed.

Headline for the archive entry is pulled from the <h1> of standard.html
for that date, so the user only needs to write the HTML files and update
index.html — the rest is automatic.
"""

import html
import os
import re
import sys
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# HTML helpers
# ---------------------------------------------------------------------------

class _H1Parser(HTMLParser):
    def __init__(self):
        super().__init__()
        self._depth = 0
        self._text = []

    def handle_starttag(self, tag, attrs):
        if tag == "h1":
            self._depth += 1

    def handle_endtag(self, tag):
        if tag == "h1" and self._depth:
            self._depth -= 1

    def handle_data(self, data):
        if self._depth:
            self._text.append(data)

    def result(self):
        return "".join(self._text).strip()


def extract_h1(path: Path) -> str:
    p = _H1Parser()
    p.feed(path.read_text(encoding="utf-8"))
    return p.result()


def display_date(date_str: str) -> str:
    """'2026-05-21' → '21 May 2026'"""
    return datetime.strptime(date_str, "%Y-%m-%d").strftime("%-d %B %Y")


# ---------------------------------------------------------------------------
# PDF generation
# ---------------------------------------------------------------------------

PRINT_CSS_STR = """
  @page { size: Letter; margin: 0.6in 0.7in 0.7in 0.7in; }
  .site-header, .site-nav, .site-footer, .toc,
  .briefing-meta .download { display: none !important; }
  body { background: white !important; }
  .briefing { padding: 0 !important; }
  .briefing-body { display: block !important; grid-template-columns: 1fr !important; }
  .container { padding: 0 !important; max-width: 100% !important; }
  h1, h2 { page-break-after: avoid; }
  table { page-break-inside: avoid; }
  .callout { page-break-inside: avoid; }
  a { color: #1F4287 !important; text-decoration: none !important; }
"""


def generate_pdfs(date_dir: Path) -> bool:
    try:
        from weasyprint import CSS, HTML as WP_HTML
    except ImportError:
        print("  weasyprint not installed — skipping PDF generation", flush=True)
        return False

    css = CSS(string=PRINT_CSS_STR)
    generated = False
    for name in ("concise", "standard", "in-depth"):
        src = date_dir / f"{name}.html"
        out = date_dir / f"{name}.pdf"
        if src.exists() and not out.exists():
            print(f"  Generating {out.name} …", flush=True)
            WP_HTML(filename=str(src), base_url=str(date_dir)).write_pdf(
                str(out), stylesheets=[css]
            )
            kb = out.stat().st_size / 1024
            print(f"  → {out.name}  ({kb:.0f} KB)", flush=True)
            generated = True
    return generated


# ---------------------------------------------------------------------------
# archive.html update
# ---------------------------------------------------------------------------

ARCHIVE_MARKER = "<!-- Future briefings will be inserted above this comment by the daily generator -->"


def update_archive(date_str: str, headline: str) -> bool:
    archive = ROOT / "archive.html"
    content = archive.read_text(encoding="utf-8")

    if f"briefings/{date_str}/" in content:
        print(f"  {date_str} already in archive.html — nothing to do", flush=True)
        return False

    escaped = html.escape(headline)

    # Add a Market Pulse link if that day's news page was archived
    news_link = ""
    if (ROOT / "news" / f"{date_str}.html").exists():
        news_link = (
            f'      <a href="news/{date_str}.html" '
            f'class="pulse-link">Market Pulse</a>\n'
        )

    new_entry = (
        f'\n  <div class="archive-item">\n'
        f'    <div class="date">{display_date(date_str)}</div>\n'
        f'    <div class="title">{escaped}</div>\n'
        f'    <div class="links">\n'
        f'      <a href="briefings/{date_str}/concise.html">Concise</a>\n'
        f'      <a href="briefings/{date_str}/standard.html">Standard</a>\n'
        f'      <a href="briefings/{date_str}/in-depth.html">In-depth</a>\n'
        f'{news_link}'
        f'    </div>\n'
        f'  </div>\n\n  {ARCHIVE_MARKER}'
    )

    updated = content.replace(ARCHIVE_MARKER, new_entry, 1)
    if updated == content:
        print("  ERROR: archive marker not found — archive.html was not updated", flush=True)
        return False

    archive.write_text(updated, encoding="utf-8")
    print(f"  Inserted {date_str} ({display_date(date_str)}) into archive.html", flush=True)
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    briefings_dir = ROOT / "briefings"
    if not briefings_dir.exists():
        print("No briefings/ directory — nothing to do.")
        return

    dates = sorted(
        [d.name for d in briefings_dir.iterdir()
         if d.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", d.name)],
        reverse=True,
    )

    if not dates:
        print("No dated briefing folders found.")
        return

    changed = False

    for date_str in dates:
        date_dir = briefings_dir / date_str
        print(f"\n[{date_str}]", flush=True)
        if generate_pdfs(date_dir):
            changed = True

    # Archive: add the most-recent date (index.html already reflects it)
    latest = dates[0]
    standard_html = briefings_dir / latest / "standard.html"
    if standard_html.exists():
        headline = extract_h1(standard_html)
        if update_archive(latest, headline):
            changed = True
    else:
        print(f"  standard.html not found for {latest} — skipping archive update")

    if not changed:
        print("\nNothing changed.")


if __name__ == "__main__":
    main()
