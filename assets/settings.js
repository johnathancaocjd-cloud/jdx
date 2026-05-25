/* JDX — settings panel.
 * Injects a gear icon into the site nav and lets visitors choose:
 *   • Theme:     light / dark / auto (follows the OS)
 *   • Text size: small / medium / large
 * Preferences persist in localStorage under jdx-theme / jdx-size.
 *
 * A tiny boot script in each page's <head> (see boot tag) reads the
 * saved values and stamps data-theme / data-size onto <html> BEFORE
 * paint, so the page never flashes the wrong theme.
 */
(function () {
  if (typeof window === 'undefined' || typeof document === 'undefined') return;

  var STORAGE_THEME = 'jdx-theme';
  var STORAGE_SIZE  = 'jdx-size';

  var html = document.documentElement;

  function read(key, fallback) {
    try { return localStorage.getItem(key) || fallback; }
    catch (e) { return fallback; }
  }
  function write(key, value) {
    try { localStorage.setItem(key, value); } catch (e) {}
  }

  function applyTheme(value) {
    html.setAttribute('data-theme', value);
    write(STORAGE_THEME, value);
  }
  function applySize(value) {
    html.setAttribute('data-size', value);
    write(STORAGE_SIZE, value);
  }

  // Defensive: in case the boot script wasn't present (e.g. older cached
  // page), set the attributes now from storage.
  if (!html.getAttribute('data-theme')) html.setAttribute('data-theme', read(STORAGE_THEME, 'auto'));
  if (!html.getAttribute('data-size'))  html.setAttribute('data-size',  read(STORAGE_SIZE,  'md'));

  // ---- UI -----------------------------------------------------------------

  function gearSVG() {
    return (
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
      + '<circle cx="12" cy="12" r="3"/>'
      + '<path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>'
      + '</svg>'
    );
  }

  function buildPanel() {
    var wrap = document.createElement('div');
    wrap.className = 'settings-wrap';
    wrap.innerHTML =
      '<button class="settings-btn" type="button" aria-label="Settings" aria-haspopup="true" aria-expanded="false">'
      + gearSVG()
      + '</button>'
      + '<div class="settings-panel" role="dialog" aria-label="Display settings">'
      +   '<div class="settings-group">'
      +     '<div class="settings-label">Appearance</div>'
      +     '<div class="settings-segments" data-group="theme" role="radiogroup" aria-label="Theme">'
      +       '<button type="button" data-value="light" role="radio">Light</button>'
      +       '<button type="button" data-value="dark"  role="radio">Dark</button>'
      +       '<button type="button" data-value="auto"  role="radio">Auto</button>'
      +     '</div>'
      +   '</div>'
      +   '<div class="settings-group">'
      +     '<div class="settings-label">Text size</div>'
      +     '<div class="settings-segments" data-group="size" role="radiogroup" aria-label="Text size">'
      +       '<button type="button" data-value="sm" role="radio" aria-label="Small">Aa</button>'
      +       '<button type="button" data-value="md" role="radio" aria-label="Medium">Aa</button>'
      +       '<button type="button" data-value="lg" role="radio" aria-label="Large">Aa</button>'
      +     '</div>'
      +   '</div>'
      + '</div>';
    return wrap;
  }

  function syncActive(panel) {
    var theme = html.getAttribute('data-theme') || 'auto';
    var size  = html.getAttribute('data-size')  || 'md';
    panel.querySelectorAll('[data-group="theme"] button').forEach(function (b) {
      var on = b.getAttribute('data-value') === theme;
      b.classList.toggle('active', on);
      b.setAttribute('aria-checked', on ? 'true' : 'false');
    });
    panel.querySelectorAll('[data-group="size"] button').forEach(function (b) {
      var on = b.getAttribute('data-value') === size;
      b.classList.toggle('active', on);
      b.setAttribute('aria-checked', on ? 'true' : 'false');
    });
  }

  function init() {
    var nav = document.querySelector('.site-nav');
    if (!nav) return;

    var wrap = buildPanel();
    nav.appendChild(wrap);

    var btn   = wrap.querySelector('.settings-btn');
    var panel = wrap.querySelector('.settings-panel');

    syncActive(panel);

    btn.addEventListener('click', function (e) {
      e.stopPropagation();
      var open = panel.classList.toggle('is-open');
      btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    });

    panel.addEventListener('click', function (e) {
      var b = e.target.closest('button[data-value]');
      if (!b) return;
      var group = b.parentElement.getAttribute('data-group');
      var value = b.getAttribute('data-value');
      if (group === 'theme') applyTheme(value);
      else if (group === 'size') applySize(value);
      syncActive(panel);
    });

    // Close on outside click or Escape
    document.addEventListener('click', function (e) {
      if (!wrap.contains(e.target)) {
        panel.classList.remove('is-open');
        btn.setAttribute('aria-expanded', 'false');
      }
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && panel.classList.contains('is-open')) {
        panel.classList.remove('is-open');
        btn.setAttribute('aria-expanded', 'false');
        btn.focus();
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
