/* In the news page: loads /data/news.json and builds the article list in the browser.
   To add an article, edit data/news.json (see the "_readme" note at its top). */
(function () {
  'use strict';

  var cfgEl = document.querySelector('[data-news-config]');
  if (!cfgEl) return;
  var cfg = JSON.parse(cfgEl.textContent);
  var list = document.querySelector('[data-news-list]');
  var filters = document.querySelector('[data-news-filters]');
  var more = document.querySelector('[data-news-more]');
  var PAGE = 8;
  var shown = PAGE;
  var pick = null;          // null = all sources
  var articles = [];
  var counts = {};
  var sources = [];
  var es = cfg.lang === 'es';

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function link(href, cls, text) {
    var a = el('a', cls, text);
    a.href = href; a.target = '_blank'; a.rel = 'noopener';
    return a;
  }
  function validDate(s) { return /^\d{4}-\d{2}-\d{2}$/.test(String(s || '')); }

  function setup(raw) {
    articles = raw
      .filter(function (a) { return a && a.url && a.title && validDate(a.date); })
      .map(function (a, i) { a._i = i; return a; })
      .sort(function (a, b) { return a.date < b.date ? 1 : a.date > b.date ? -1 : a._i - b._i; });
    counts = {};
    articles.forEach(function (a) { counts[a.source] = (counts[a.source] || 0) + 1; });
    sources = Object.keys(counts).sort(function (a, b) { return counts[b] - counts[a] || a.localeCompare(b); });
  }

  function renderFilters() {
    filters.textContent = '';
    [null].concat(sources).forEach(function (name) {
      var b = el('button', 'news-filter__btn');
      b.type = 'button';
      b.setAttribute('aria-pressed', String(name === pick));
      b.appendChild(el('span', '', name === null ? cfg.all : name));
      b.appendChild(el('span', 'news-filter__count', String(name === null ? articles.length : counts[name])));
      b.addEventListener('click', function () { pick = name; shown = PAGE; renderFilters(); renderList(); });
      filters.appendChild(b);
    });
  }

  function renderList() {
    list.textContent = '';
    list.setAttribute('aria-busy', 'false');
    var items = articles.filter(function (a) { return pick === null || a.source === pick; });
    if (!items.length) list.appendChild(el('p', 'news-feed__status', cfg.empty));

    items.slice(0, shown).forEach(function (a) {
      var row = el('article', 'news-item');
      var parts = a.date.split('-');

      var date = el('p', 'news-item__date');
      var time = el('time');
      time.dateTime = a.date;
      time.appendChild(el('span', 'news-item__month', cfg.months[+parts[1] - 1]));
      time.appendChild(el('span', 'news-item__day', String(+parts[2])));
      date.appendChild(time);
      row.appendChild(date);

      var body = el('div', 'news-item__body');
      body.appendChild(el('span', 'news-item__source', a.source));
      var h = el('h2', 'news-item__title');
      h.appendChild(link(a.url, '', (es && a.title_es) || a.title));
      body.appendChild(h);
      var summary = (es && a.summary_es) || a.summary;
      if (summary) body.appendChild(el('p', 'news-item__summary', summary));

      var links = el('p', 'news-item__links');
      links.appendChild(link(a.url, 'news-item__read', cfg.read + ' ' + (a.site || a.source) + ' ↗'));
      if (a.alt_url) {
        links.appendChild(document.createTextNode(' · '));
        links.appendChild(link(a.alt_url, 'news-item__read', ((es && a.alt_label_es) || a.alt_label || a.alt_url) + ' ↗'));
      }
      body.appendChild(links);
      row.appendChild(body);
      list.appendChild(row);
    });
    more.hidden = items.length <= shown;
  }

  more.addEventListener('click', function () {
    var firstNew = shown;
    shown += PAGE;
    renderList();
    var next = list.children[firstNew] && list.children[firstNew].querySelector('a');
    if (next) next.focus({ preventScroll: false });
  });

  fetch(cfg.src, { cache: 'no-cache' })
    .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(function (data) {
      setup(Array.isArray(data) ? data : (data.articles || []));
      renderFilters();
      renderList();
    })
    .catch(function () {
      list.setAttribute('aria-busy', 'false');
      list.textContent = '';
      list.appendChild(el('p', 'news-feed__status', cfg.error));
    });
})();
