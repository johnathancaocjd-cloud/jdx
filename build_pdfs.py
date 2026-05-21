"""
Render the three JDX briefing HTML pages to PDF using weasyprint.
This keeps the HTML as the single source of truth — PDFs are derived from it.
"""

from weasyprint import HTML, CSS
import os

BASE = "/sessions/dreamy-serene-ramanujan/mnt/outputs/jdx/briefings/2026-05-21"

# Print-specific CSS overrides: hide the nav/TOC/footer, tighten margins,
# remove the sticky header so it doesn't repeat on every page.
PRINT_CSS = CSS(string="""
  @page { size: Letter; margin: 0.6in 0.7in 0.7in 0.7in; }
  .site-header, .site-nav, .site-footer, .toc, .briefing-meta .download { display: none !important; }
  body { background: white !important; }
  .briefing { padding: 0 !important; }
  .briefing-body { display: block !important; grid-template-columns: 1fr !important; }
  .container { padding: 0 !important; max-width: 100% !important; }
  h1, h2 { page-break-after: avoid; }
  table { page-break-inside: avoid; }
  .callout { page-break-inside: avoid; }
  a { color: #1F4287 !important; text-decoration: none !important; }
  .briefing-header { margin-bottom: 18px !important; padding-bottom: 14px !important; }
  /* Add a small page header */
  @page { @top-right { content: "JDX · 21 May 2026"; font-family: Georgia, serif; font-size: 9pt; color: #5C677D; } }
  @page { @bottom-right { content: "Page " counter(page) " of " counter(pages); font-family: 'SF Mono', Menlo, monospace; font-size: 8pt; color: #8DA2C0; } }
""")

for name in ["concise", "standard", "in-depth"]:
    src = f"{BASE}/{name}.html"
    out = f"{BASE}/{name}.pdf"
    HTML(filename=src, base_url=BASE).write_pdf(out, stylesheets=[PRINT_CSS])
    size_kb = os.path.getsize(out) / 1024
    print(f"  {name:10s} -> {out}  ({size_kb:.1f} KB)")

print("Done.")
