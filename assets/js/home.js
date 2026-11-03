/* Home page behavior: hero slideshow, live signature count, share dialog. */
(function () {
  'use strict';

  var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---------- Hero slideshow ---------- */
  (function slideshow() {
    var slides = Array.prototype.slice.call(document.querySelectorAll('.hero__slide'));
    if (slides.length < 2) return;
    var current = 0;
    var INTERVAL = 12000;

    function load(i) {
      var s = slides[i];
      if (s && !s.style.backgroundImage) s.style.backgroundImage = "url('" + s.getAttribute('data-src') + "')";
    }
    function show(next) {
      load(next);
      slides[current].classList.remove('is-active');
      var el = slides[next];
      el.style.animation = 'none';
      void el.offsetWidth;             // restart the slow zoom
      el.style.animation = '';
      el.classList.add('is-active');
      current = next;
      load((next + 1) % slides.length); // preload the one after
    }
    load(1);
    var timer = setInterval(function () { show((current + 1) % slides.length); }, INTERVAL);
    // Save data and battery: pause while the tab is hidden
    document.addEventListener('visibilitychange', function () {
      if (document.hidden) { clearInterval(timer); timer = null; }
      else if (!timer) timer = setInterval(function () { show((current + 1) % slides.length); }, INTERVAL);
    });
  })();

  /* ---------- Live signature count (Google Apps Script, JSONP) ---------- */
  var count = 0;
  (function signatures() {
    var box = document.querySelector('[data-signature-count]');
    if (!box) return;
    var src = box.getAttribute('data-src');
    var num = box.querySelector('.sig-count__number');
    var locale = document.documentElement.lang === 'es' ? 'es-US' : 'en-US';
    var cb = 'fbeSigCount' + Date.now();
    var fmt = function (n) { return Math.round(n).toLocaleString(locale); };

    function render(n) {
      if (!(n > 0) || n === count) return;
      var from = count;
      count = n;
      box.hidden = false;
      if (reduceMotion) { num.textContent = fmt(n); return; }
      var t0 = null, dur = from ? 600 : 1200;
      function step(t) {
        if (!t0) t0 = t;
        var k = Math.min(1, (t - t0) / dur);
        num.textContent = fmt(from + (n - from) * (1 - Math.pow(1 - k, 3)));
        if (k < 1) requestAnimationFrame(step);
      }
      requestAnimationFrame(step);
    }
    window[cb] = function (d) { if (d && d.count != null) render(Number(d.count)); };
    function load() {
      var s = document.createElement('script');
      s.src = src + (src.indexOf('?') < 0 ? '?' : '&') + 'callback=' + cb + '&t=' + Date.now();
      s.async = true;
      s.onload = s.onerror = function () { s.remove(); };
      document.head.appendChild(s);
    }
    load();
    setInterval(function () { if (!document.hidden) load(); }, 60000);
  })();

  /* ---------- Share dialog ---------- */
  (function share() {
    var dialog = document.querySelector('dialog[data-share]');
    if (!dialog) return;
    var T = JSON.parse(dialog.querySelector('[data-share-text]').textContent);
    var SITE = dialog.getAttribute('data-url');
    var status = dialog.querySelector('[data-share-status]');
    var imgBox = dialog.querySelector('[data-share-image]');
    var enc = encodeURIComponent;
    var locale = document.documentElement.lang === 'es' ? 'es-US' : 'en-US';

    function message() {
      return T.a + (count ? T.b.replace('{n}', count.toLocaleString(locale)) : '') + T.c + SITE;
    }
    function say(text) {
      status.textContent = text;
      clearTimeout(say.t);
      say.t = setTimeout(function () { status.textContent = ''; }, 6000);
    }
    function copy(text) {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        return navigator.clipboard.writeText(text).then(function () { return true; }, function () { return legacyCopy(text); });
      }
      return Promise.resolve(legacyCopy(text));
    }
    function legacyCopy(text) {
      var x = document.createElement('textarea');
      x.value = text; x.setAttribute('readonly', '');
      x.style.cssText = 'position:fixed;left:-9999px;top:0';
      document.body.appendChild(x); x.select();
      var ok = false; try { ok = document.execCommand('copy'); } catch (e) {}
      x.remove(); return ok;
    }
    var URLS = {
      fb: function () { return 'https://www.facebook.com/sharer/sharer.php?u=' + enc(SITE); },
      x: function (t) { return 'https://x.com/intent/tweet?text=' + enc(t); }
    };
    dialog.querySelectorAll('a[data-network]').forEach(function (a) {
      var n = a.getAttribute('data-network');
      a.addEventListener('click', function () {
        var t = message();
        a.href = URLS[n](t);
        if (n === 'fb') copy(t).then(function (ok) { say(ok ? T.fb : T.fbNo); });
      });
      a.href = URLS[n](message());
    });

    // Instagram: draw a square image the visitor can save and post
    function card() {
      var c = document.createElement('canvas'); c.width = c.height = 1080;
      var g = c.getContext('2d');
      g.fillStyle = '#13224F'; g.fillRect(0, 0, 1080, 1080);
      g.fillStyle = '#D9B96E'; g.fillRect(0, 0, 1080, 18);
      g.textBaseline = 'top';
      g.fillStyle = '#fff'; g.font = '900 34px Archivo, "Arial Black", sans-serif';
      g.fillText('★  FOR A BRIGHTER EVANSTON', 90, 110);
      g.fillStyle = '#D9B96E'; g.font = '900 112px Archivo, "Arial Black", sans-serif';
      var y = 250;
      T.big.forEach(function (line) { g.fillText(line, 90, y); y += 124; });
      g.fillStyle = '#fff'; g.font = '400 40px "Public Sans", Arial, sans-serif'; y += 40;
      function wrap(text) {
        var line = '';
        text.split(' ').forEach(function (w) {
          var test = line ? line + ' ' + w : w;
          if (g.measureText(test).width > 900) { g.fillText(line, 90, y); y += 54; line = w; } else line = test;
        });
        if (line) { g.fillText(line, 90, y); y += 54; }
      }
      wrap(T.sub);
      if (count) {
        y += 20; g.fillStyle = '#D9B96E'; g.font = '700 40px "Public Sans", Arial, sans-serif';
        wrap(T.cnt.replace('{n}', count.toLocaleString(locale)));
      }
      g.fillStyle = '#D9B96E'; g.fillRect(0, 900, 1080, 180);
      g.fillStyle = '#13224F'; g.font = '900 46px Archivo, "Arial Black", sans-serif';
      g.fillText(T.cta, 90, 935);
      g.font = '700 38px "Public Sans", Arial, sans-serif';
      g.fillText(SITE.replace(/^https?:\/\//, '').replace(/\/$/, ''), 90, 1000);
      return c;
    }
    dialog.querySelector('[data-network="img"]').addEventListener('click', function () {
      var go = function () {
        var url = card().toDataURL('image/png');
        imgBox.querySelector('img').src = url;
        imgBox.hidden = false;
        copy(message());
        var a = document.createElement('a');
        a.href = url; a.download = T.png;
        document.body.appendChild(a);
        try { a.click(); } catch (e) {}
        a.remove();
        say(T.igDl);
      };
      if (document.fonts && document.fonts.ready) document.fonts.ready.then(go); else go();
    });
    dialog.addEventListener('close', function () { imgBox.hidden = true; status.textContent = ''; });
  })();
})();
