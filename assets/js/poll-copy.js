/* URL-only clipboard action, loaded on the two poll pages only. */
(function () {
  'use strict';
  var path = window.location.pathname.replace(/^\/sandbox\/[^/]+(?=\/)/, '');
  if (path !== '/home/voter-poll/' && path !== '/es/encuesta/') return;
  var trigger = document.querySelector('[data-poll-copy]');
  if (!trigger) return;

  function copyFallback(url) {
    var field = document.createElement('textarea');
    field.value = url;
    field.setAttribute('readonly', '');
    field.setAttribute('aria-hidden', 'true');
    field.style.cssText = 'position:fixed;left:-9999px;top:0';
    document.body.appendChild(field);
    field.select();
    var copied = false;
    try { copied = document.execCommand('copy'); } catch (error) {}
    field.remove();
    trigger.focus();
    if (!copied) window.prompt(trigger.textContent.trim(), url);
  }

  trigger.addEventListener('click', function () {
    var url = window.location.href;
    if (!navigator.clipboard || !navigator.clipboard.writeText) {
      copyFallback(url);
      return;
    }
    try {
      navigator.clipboard.writeText(url).catch(function () { copyFallback(url); });
    } catch (error) { copyFallback(url); }
  });
})();
