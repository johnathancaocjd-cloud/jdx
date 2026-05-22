/* JDX — Stock Lookup
 * Universal search powered by free TradingView widgets, plus JDX AI "takes"
 * for the curated watchlist loaded from data/stocks.json.
 */
(() => {
  "use strict";

  const TV = {
    info:    "https://s3.tradingview.com/external-embedding/embed-widget-symbol-info.js",
    chart:   "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js",
    tech:    "https://s3.tradingview.com/external-embedding/embed-widget-technical-analysis.js",
    profile: "https://s3.tradingview.com/external-embedding/embed-widget-symbol-profile.js",
    fin:     "https://s3.tradingview.com/external-embedding/embed-widget-financials.js",
  };

  let watchlist = [];
  const byTicker = {};
  let generatedDisplay = "";

  const $ = (id) => document.getElementById(id);
  const escapeHtml = (s) => String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));

  /* ---- TradingView widget rendering ---- */
  function buildWidget(hostId, src, config) {
    const host = $(hostId);
    if (!host) return;
    host.innerHTML = "";
    const container = document.createElement("div");
    container.className = "tradingview-widget-container";
    const widget = document.createElement("div");
    widget.className = "tradingview-widget-container__widget";
    const copy = document.createElement("div");
    copy.className = "tradingview-widget-copyright";
    copy.innerHTML =
      '<a href="https://www.tradingview.com/" rel="noopener nofollow" ' +
      'target="_blank">Track all markets on TradingView</a>';
    const script = document.createElement("script");
    script.src = src;
    script.async = true;
    script.textContent = JSON.stringify(config);
    container.append(widget, copy, script);
    host.appendChild(container);
  }

  function renderWidgets(symbol) {
    buildWidget("w-info", TV.info, {
      symbol, width: "100%", locale: "en", colorTheme: "light", isTransparent: true,
    });
    buildWidget("w-chart", TV.chart, {
      width: "100%", height: 500, symbol, interval: "D", timezone: "Etc/UTC",
      theme: "light", style: "1", locale: "en", hide_side_toolbar: false,
      allow_symbol_change: false, support_host: "https://www.tradingview.com",
    });
    buildWidget("w-tech", TV.tech, {
      interval: "1D", width: "100%", height: 450, isTransparent: true, symbol,
      showIntervalTabs: true, displayMode: "single", locale: "en", colorTheme: "light",
    });
    buildWidget("w-profile", TV.profile, {
      symbol, width: "100%", height: 450, isTransparent: true,
      colorTheme: "light", locale: "en",
    });
    buildWidget("w-fin", TV.fin, {
      symbol, displayMode: "regular", width: "100%", height: 500,
      isTransparent: true, colorTheme: "light", locale: "en",
    });
  }

  /* ---- JDX take ---- */
  function renderTake(stock, ticker) {
    const box = $("jdx-take");
    if (!box) return;
    if (stock && stock.summary) {
      box.className = "jdx-take has-take";
      box.innerHTML =
        `<div class="jdx-take-label">JDX Take</div>` +
        `<p>${escapeHtml(stock.summary)}</p>` +
        `<div class="jdx-take-foot">JDX watchlist` +
        (generatedDisplay ? ` &middot; updated ${escapeHtml(generatedDisplay)}` : ``) +
        `</div>`;
    } else if (stock) {
      box.className = "jdx-take pending";
      box.innerHTML =
        `<div class="jdx-take-label">JDX Take</div>` +
        `<p>JDX's take on ${escapeHtml(stock.name)} publishes with the next ` +
        `daily update at 09:00 HKT.</p>`;
    } else {
      box.className = "jdx-take generic";
      box.innerHTML =
        `<div class="jdx-take-label">JDX Take</div>` +
        `<p><strong>${escapeHtml(ticker)}</strong> isn't on the JDX watchlist, ` +
        `so there's no daily written take — but the live chart, key stats, ` +
        `technicals and financials below cover it in full.</p>`;
    }
  }

  /* ---- select & render a stock ---- */
  function showStock(rawTicker, opts = {}) {
    const ticker = String(rawTicker || "").trim().toUpperCase();
    if (!ticker) return;
    const stock = byTicker[ticker] || null;
    const symbol = stock ? stock.tv_symbol : ticker;

    $("stock-result").hidden = false;
    $("sr-title").textContent = stock ? `${ticker} · ${stock.name}` : ticker;
    const sectorEl = $("sr-sector");
    if (stock) {
      sectorEl.textContent = stock.sector;
      sectorEl.hidden = false;
    } else {
      sectorEl.hidden = true;
    }

    renderTake(stock, ticker);
    renderWidgets(symbol);

    document.querySelectorAll(".watchlist-chip").forEach((c) => {
      c.classList.toggle("active", c.dataset.ticker === ticker);
    });

    history.replaceState(null, "", "#" + ticker);
    if (opts.scroll) {
      $("stock-result").scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  /* ---- watchlist chips ---- */
  function renderWatchlist() {
    const grid = $("watchlist-grid");
    if (!grid) return;
    if (!watchlist.length) {
      grid.innerHTML =
        `<p class="watchlist-empty">The watchlist populates with the next ` +
        `daily update — search any ticker above in the meantime.</p>`;
      return;
    }
    grid.innerHTML = "";
    watchlist.forEach((s) => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "watchlist-chip";
      chip.dataset.ticker = s.ticker;
      chip.innerHTML =
        `<span class="wc-ticker">${escapeHtml(s.ticker)}</span>` +
        `<span class="wc-name">${escapeHtml(s.name)}</span>`;
      chip.addEventListener("click", () => showStock(s.ticker, { scroll: true }));
      grid.appendChild(chip);
    });
  }

  /* ---- search box ---- */
  function initSearch() {
    const input = $("stock-search-input");
    const form = $("stock-search-form");
    const list = $("ticker-options");
    if (list) {
      list.innerHTML = watchlist
        .map((s) => `<option value="${escapeHtml(s.ticker)}">${escapeHtml(s.name)}</option>`)
        .join("");
    }
    if (form) {
      form.addEventListener("submit", (e) => {
        e.preventDefault();
        showStock(input.value, { scroll: true });
        input.blur();
      });
    }
  }

  /* ---- init ---- */
  async function init() {
    try {
      const res = await fetch("data/stocks.json", { cache: "no-cache" });
      if (res.ok) {
        const data = await res.json();
        watchlist = Array.isArray(data.stocks) ? data.stocks : [];
        generatedDisplay = data.generated_display || "";
        watchlist.forEach((s) => { byTicker[s.ticker] = s; });
      }
    } catch (e) {
      console.warn("stocks.json unavailable:", e);
    }
    renderWatchlist();
    initSearch();

    const hash = decodeURIComponent((location.hash || "").replace(/^#/, "")).toUpperCase();
    const start = hash || (watchlist[0] && watchlist[0].ticker) || "AAPL";
    showStock(start, { scroll: false });
  }

  document.addEventListener("DOMContentLoaded", init);
})();
