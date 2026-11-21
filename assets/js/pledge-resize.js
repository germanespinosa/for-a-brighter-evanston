/* For partner sites: makes the For a Brighter Evanston pledge iframe as tall
   as its content, so it never shows scroll bars. Optional: without it the
   iframe keeps the height set in the snippet. */
(function () {
  'use strict';
  window.addEventListener('message', function (e) {
    var d = e.data;
    if (!d || d.type !== 'fabe-pledge:height' || typeof d.height !== 'number') return;
    if (!/^https:\/\/([a-z0-9-]+\.)*forabrighterevanston\.org$/.test(e.origin) && e.origin !== window.location.origin) return;
    var frames = document.getElementsByTagName('iframe');
    for (var i = 0; i < frames.length; i++) {
      if (frames[i].contentWindow === e.source) {
        frames[i].style.height = Math.max(120, Math.min(d.height, 4000)) + 'px';
      }
    }
  });
})();
