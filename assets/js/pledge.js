/* Referendum pledge: live counter, form, language toggle, sharing, and
   iframe auto-height. Talks to the Apps Script in apps-script/pledge/. */
(function () {
  'use strict';

  var params = new URLSearchParams(location.search);
  var inFrame = window.parent !== window;
  function readCopy(root) {
    var el = root.querySelector('[data-pl-copy]');
    try { return JSON.parse(el.textContent); } catch (e) { return null; }
  }

  function fmt(n) {
    return Number(n).toLocaleString('en-US');
  }

  // ---------------------------------------------------------------- counter
  var countRequest = null;
  function fetchCount(endpoint) {
    if (!endpoint) return Promise.reject(new Error('not connected'));
    if (!countRequest) {
      countRequest = fetch(endpoint + (endpoint.indexOf('?') < 0 ? '?' : '&') + 'action=count', { credentials: 'omit' })
        .then(function (r) { return r.json(); })
        .then(function (d) { if (!d || !d.ok || typeof d.count !== 'number') throw new Error('bad'); return d.count; });
    }
    return countRequest;
  }

  function showCount(root, n) {
    root.querySelectorAll('[data-pl-count]').forEach(function (el) {
      el.textContent = fmt(n);
      el.hidden = false;
    });
    resize();
  }

  // ---------------------------------------------------------------- language
  function applyLang(root, copy, lang) {
    var c = copy[lang];
    if (!c) return;
    root.setAttribute('data-lang', lang);
    if (root.hasAttribute('data-pledge')) document.documentElement.lang = lang;
    root.querySelectorAll('[data-t]').forEach(function (el) {
      var key = el.getAttribute('data-t');
      if (c[key] !== undefined) el.textContent = c[key];
    });
    root.querySelectorAll('[data-t-attr]').forEach(function (el) {
      var parts = el.getAttribute('data-t-attr').split(':');
      if (c[parts[1]] !== undefined) el.setAttribute(parts[0], c[parts[1]]);
    });
    root.querySelectorAll('[data-href]').forEach(function (el) {
      var site = root.getAttribute('data-site') || '/';
      var path = c[el.getAttribute('data-href')] || '/';
      el.href = new URL(path.replace(/^\//, ''), site).href + (el.getAttribute('data-hash') || '');
    });
    root.querySelectorAll('[data-lang-btn]').forEach(function (b) {
      b.setAttribute('aria-pressed', String(b.getAttribute('data-lang-btn') === lang));
    });
    resize();
  }

  // ---------------------------------------------------------------- links out
  // On our own pages the card sits in an iframe: links replace the whole page.
  // On partner sites they open in a new tab.
  function setLinkTargets(root, source) {
    var own = source === 'fabe';
    root.querySelectorAll('[data-pl-out]').forEach(function (a) {
      if (!inFrame) return;
      if (own) { a.target = '_top'; } else { a.target = '_blank'; a.rel = 'noopener'; }
    });
    var brand = root.querySelector('[data-pl-brand]');
    if (brand) brand.hidden = own || !inFrame;
  }

  // ---------------------------------------------------------------- card
  function initCard(root) {
    var copy = readCopy(root);
    if (!copy) return;
    var endpoint = root.getAttribute('data-endpoint');
    var sitekey = root.getAttribute('data-sitekey');
    var lang = params.get('lang') === 'es' ? 'es' : (params.get('lang') === 'en' ? 'en' : root.getAttribute('data-lang'));
    var source = (params.get('source') || (inFrame ? 'unknown' : 'direct')).toLowerCase().replace(/[^a-z0-9_-]/g, '').slice(0, 40) || 'unknown';
    var started = Date.now();
    var form = root.querySelector('[data-pl-form]');
    var msg = root.querySelector('[data-pl-msg]');
    var done = root.querySelector('[data-pl-done]');
    var doneMsg = root.querySelector('[data-pl-done-msg]');
    var button = form.querySelector('button[type=submit]');
    var turnstileToken = '';
    var state = null;

    applyLang(root, copy, lang);
    setLinkTargets(root, source);

    root.querySelectorAll('[data-lang-btn]').forEach(function (b) {
      b.addEventListener('click', function () {
        lang = b.getAttribute('data-lang-btn');
        applyLang(root, copy, lang);
        if (state) doneMsg.textContent = copy[lang][state];
        updateShare();
      });
    });

    fetchCount(endpoint).then(function (n) { showCount(root, n); }).catch(function () { /* stay blank, never zero */ });

    if (sitekey) {
      var box = root.querySelector('[data-pl-turnstile]');
      box.hidden = false;
      window.fabePledgeTurnstile = function () {
        window.turnstile.render(box, { sitekey: sitekey, callback: function (t) { turnstileToken = t; } });
        resize();
      };
      var s = document.createElement('script');
      s.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?onload=fabePledgeTurnstile';
      s.async = true;
      document.head.appendChild(s);
    }

    function shareUrl() { return new URL(copy[lang].page_url.replace(/^\//, ''), root.getAttribute('data-site')).href; }
    function updateShare() {
      var c = copy[lang];
      var url = shareUrl();
      var text = c.share_body + ' ' + url;
      root.querySelector('[data-share=sms]').href = 'sms:?&body=' + encodeURIComponent(text);
      root.querySelector('[data-share=email]').href = 'mailto:?subject=' + encodeURIComponent(c.share_subject) + '&body=' + encodeURIComponent(text);
      root.querySelector('[data-share=facebook]').href = 'https://www.facebook.com/sharer/sharer.php?u=' + encodeURIComponent(url);
    }
    updateShare();

    root.querySelector('[data-share=copy]').addEventListener('click', function () {
      var note = root.querySelector('[data-pl-copied]');
      var url = shareUrl();
      var ok = function () { note.textContent = copy[lang].copied; };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(url).then(ok, function () { note.textContent = url; });
      } else {
        note.textContent = url;
      }
    });

    function finish(kind) {
      state = kind;
      form.hidden = true;
      doneMsg.textContent = copy[lang][kind];
      done.hidden = false;
      done.focus();
      resize();
    }

    function fail(key) {
      msg.textContent = copy[lang][key];
      button.disabled = false;
      button.textContent = copy[lang].button;
      resize();
    }

    form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      msg.textContent = '';
      var first = form.first.value.trim();
      var last = form.last.value.trim();
      var email = form.email.value.trim();
      var bad = null;
      [[form.first, first], [form.last, last], [form.email, email && form.email.checkValidity() ? email : '']].forEach(function (pair) {
        pair[0].setAttribute('aria-invalid', pair[1] ? 'false' : 'true');
        if (!pair[1] && !bad) bad = pair[0];
      });
      if (bad) { fail('invalid'); bad.focus(); return; }
      if (!endpoint) { fail('error'); return; }
      if (sitekey && !turnstileToken) { fail('error'); return; }

      button.disabled = true;
      button.textContent = copy[lang].sending;
      fetch(endpoint, {
        method: 'POST',
        credentials: 'omit',
        // text/plain keeps this a "simple" request that Apps Script accepts.
        body: JSON.stringify({
          first: first, last: last, email: email,
          optin: form.optin.checked, lang: lang, source: source,
          website: form.website.value, elapsed: Date.now() - started,
          turnstile: turnstileToken
        })
      })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (!d || !d.ok) { fail('error'); return; }
          if (typeof d.count === 'number') showCount(root, d.count);
          finish(d.already ? 'already' : 'thanks');
        })
        .catch(function () { fail('error'); });
    });
  }

  // ---------------------------------------------------------------- counter only
  function initCounter(root) {
    var copy = readCopy(root);
    var lang = params.get('lang') === 'es' ? 'es' : root.getAttribute('data-lang');
    if (copy && lang !== root.getAttribute('data-lang')) applyLang(root, copy, lang);
    var source = (params.get('source') || '').toLowerCase();
    setLinkTargets(root, source === 'fabe' ? 'fabe' : 'partner');
    fetchCount(root.getAttribute('data-endpoint')).then(function (n) { showCount(root, n); }).catch(function () {});
  }

  // ---------------------------------------------------------------- iframe height
  var lastHeight = 0;
  function resize() {
    if (!inFrame) return;
    var h = Math.ceil(document.documentElement.getBoundingClientRect().height);
    if (h === lastHeight) return;
    lastHeight = h;
    window.parent.postMessage({ type: 'fabe-pledge:height', height: h }, '*');
  }

  document.querySelectorAll('[data-pledge]').forEach(initCard);
  document.querySelectorAll('[data-pledge-counter]').forEach(initCounter);
  if (inFrame) {
    if (window.ResizeObserver) new ResizeObserver(resize).observe(document.documentElement);
    window.addEventListener('load', resize);
    resize();
  }
})();
