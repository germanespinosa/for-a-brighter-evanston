/* Write to the Board page: builds a personalized letter and hands it to the
   visitor's own email (Gmail on desktop, the mail app on phones) or copies it.
   Nothing typed here is stored or sent anywhere by this site.
   All wording lives in assets/js/letter-content.js. */
(function () {
  'use strict';

  var root = document.querySelector('[data-letter]');
  if (!root || !window.LETTER_CONTENT) return;

  var LANG = root.getAttribute('data-lang') === 'es' ? 'es' : 'en';
  var C = window.LETTER_CONTENT[LANG];
  var BOARD = window.LETTER_CONTENT.board;
  var T = C.ui;
  var ISSUES = C.issues;

  /* ---------- Fill in labels ---------- */
  root.querySelectorAll('[data-ui]').forEach(function (n) { n.textContent = T[n.getAttribute('data-ui')] || ''; });
  root.querySelectorAll('[data-ui-placeholder]').forEach(function (n) { n.placeholder = T[n.getAttribute('data-ui-placeholder')] || ''; });

  var issuesBox = root.querySelector('[data-issues]');
  ISSUES.forEach(function (issue, i) {
    var label = document.createElement('label');
    label.className = 'choice';
    label.innerHTML = '<input type="radio" name="issue" value="' + i + '"' + (i === 0 ? ' checked' : '') + '>' +
      '<span><span class="choice__title"></span><span class="choice__desc"></span></span>';
    label.querySelector('.choice__title').textContent = issue.title;
    label.querySelector('.choice__desc').textContent = issue.desc;
    issuesBox.appendChild(label);
  });

  var rolesBox = root.querySelector('[data-roles]');
  T.roles.forEach(function (r, i) {
    var label = document.createElement('label');
    label.className = 'chip';
    label.innerHTML = '<input type="radio" name="role" value="' + i + '"' + (i === 0 ? ' checked' : '') + '><span></span>';
    label.querySelector('span').textContent = r;
    rolesBox.appendChild(label);
  });

  var MOBILE = /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent) ||
    (navigator.maxTouchPoints > 1 && /Macintosh/.test(navigator.userAgent));
  if (MOBILE) root.querySelector('[data-send-row]').classList.add('is-mobile');
  root.querySelector('[data-send-sub]').textContent = MOBILE ? T.msub : T.dsub;
  root.querySelector('[data-send-note]').textContent = MOBILE ? T.mnote : T.dnote;

  /* ---------- Letter assembly ---------- */
  var nameInput = document.getElementById('letter-name');
  var subject = document.getElementById('letter-subject');
  var body = document.getElementById('letter-body');
  var status = root.querySelector('[data-status]');
  var pick = {}, edited = false, lastName = '', warned = false;

  function rnd(n, avoid) { if (n < 2) return 0; var x; do { x = Math.floor(Math.random() * n); } while (x === avoid); return x; }
  function two(n, prev) {
    var a = rnd(n, prev ? prev[0] : -1), b;
    do { b = Math.floor(Math.random() * n); } while (b === a);
    return a < b ? [a, b] : [b, a];
  }
  function checked(name) { var r = root.querySelector('input[name=' + name + ']:checked'); return r ? +r.value : 0; }
  function nameVal() { return nameInput.value.trim() || T.namePlace; }

  function opening(i, topic) {
    var aTopic = /^el /.test(topic) ? 'al ' + topic.slice(3) : 'a ' + topic;
    return C.openings[i].replace('{x}', topic).replace('{a_x}', aTopic);
  }

  function build() {
    var n = nameVal(), x = ISSUES[pick.i];
    var parts = [
      T.greet,
      opening(pick.o, x.topic),
      C.who[checked('role')].replace('{name}', n),
      x.concerns[pick.c[0]] + ' ' + x.concerns[pick.c[1]],
      x.facts[pick.f[0]] + ' ' + x.facts[pick.f[1]],
      x.asks[pick.a]
    ];
    if (!x.closures) parts.push(C.common);
    parts.push(C.closings[pick.k]);
    return parts.join('\n\n') + '\n\n' + T.signoff + '\n' + n;
  }

  function say(text, warn) { status.textContent = text; status.classList.toggle('is-warning', !!warn); }

  function grow() {
    body.style.height = 'auto';
    body.style.height = Math.max(320, body.scrollHeight + 4) + 'px';
  }

  function shuffle(first) {
    var i = checked('issue'), same = !first && pick.i === i;
    var x = ISSUES[i];
    pick = {
      i: i,
      s: rnd(x.subjects.length, same ? pick.s : -1),
      o: rnd(C.openings.length, same ? pick.o : -1),
      c: two(x.concerns.length, same ? pick.c : null),
      f: two(x.facts.length, same ? pick.f : null),
      a: rnd(x.asks.length, same ? pick.a : -1),
      k: rnd(C.closings.length, same ? pick.k : -1)
    };
    subject.value = x.subjects[pick.s];
    body.value = build();
    edited = false; lastName = nameVal(); warned = false;
    say('');
    grow();
  }

  body.addEventListener('input', function () { edited = true; warned = false; grow(); });

  nameInput.addEventListener('input', function () {
    var n = nameVal();
    if (!edited) body.value = build();
    else if (lastName && n !== lastName) body.value = body.value.split(lastName).join(n);
    lastName = n;
  });

  root.querySelectorAll('input[name=role]').forEach(function (r) {
    r.addEventListener('change', function () {
      if (!edited) { body.value = build(); return; }
      var n = nameVal(), want = C.who[checked('role')].replace('{name}', n);
      for (var i = 0; i < C.who.length; i++) {
        var old = C.who[i].replace('{name}', n);
        if (i !== checked('role') && body.value.indexOf(old) >= 0) { body.value = body.value.replace(old, want); break; }
      }
    });
  });

  root.querySelectorAll('input[name=issue]').forEach(function (r) {
    r.addEventListener('change', function () {
      var was = edited;
      shuffle(false);
      if (was) say(T.swapped);
    });
  });

  root.querySelector('[data-shuffle]').addEventListener('click', function () { shuffle(false); });
  root.querySelector('[data-letter-form]').addEventListener('submit', function (e) { e.preventDefault(); });

  /* ---------- Send / copy ---------- */
  var enc = encodeURIComponent, to = BOARD.join(',');
  function mailtoUrl() { return 'mailto:' + to + '?subject=' + enc(subject.value) + '&body=' + enc(body.value); }
  function gmailUrl() { return 'https://mail.google.com/mail/?view=cm&fs=1&to=' + enc(to) + '&su=' + enc(subject.value) + '&body=' + enc(body.value); }

  function ready() {
    if (!nameInput.value.trim()) { say(T.needName, true); nameInput.focus(); return false; }
    if (/\[[^\]]{3,}\]/.test(body.value) && !warned) { warned = true; say(T.brackets, true); body.focus(); return false; }
    return true;
  }

  root.querySelector('[data-send]').addEventListener('click', function () {
    if (!ready()) return;
    if (MOBILE) window.location.href = mailtoUrl();
    else window.open(gmailUrl(), '_blank', 'noopener');
    say(T.opened);
  });

  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text).then(function () { return true; }, function () { return legacy(); });
    }
    return Promise.resolve(legacy());
    function legacy() {
      var x = document.createElement('textarea');
      x.value = text; x.setAttribute('readonly', '');
      x.style.cssText = 'position:fixed;left:-9999px;top:0';
      document.body.appendChild(x); x.select();
      var ok = false; try { ok = document.execCommand('copy'); } catch (e) {}
      x.remove(); return ok;
    }
  }

  root.querySelector('[data-copy]').addEventListener('click', function () {
    if (!ready()) return;
    copyText(T.copyHead + BOARD.join(', ') + '\n' + T.copySubj + subject.value + '\n\n' + body.value).then(function (ok) {
      say(ok ? T.copied : T.copyFail, !ok);
      if (!ok) { body.focus(); body.select(); }
    });
  });

  window.addEventListener('resize', grow);
  shuffle(true);
})();
