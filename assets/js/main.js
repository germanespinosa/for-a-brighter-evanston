/* For A Brighter Evanston — shared behavior for every page.
   - Opens/closes <dialog> windows (buttons with data-dialog-open="<id>")
   - Shows a thank-you message after Google Forms submit (forms with data-google-form)
   - Closes the "Add to calendar" menu on outside click or Escape */
(function () {
  'use strict';

  /* ---------- Dialogs ---------- */
  var opener = null;

  function openDialog(dialog, trigger) {
    if (!dialog || dialog.open) return;
    opener = trigger || document.activeElement;
    if (typeof dialog.showModal === 'function') {
      dialog.showModal();
    } else {
      dialog.setAttribute('open', '');   // very old browsers: show inline
    }
    document.documentElement.classList.add('has-dialog');
    var first = dialog.querySelector('input:not([type=hidden]), textarea, button:not(.dialog__close), a[href]');
    if (first && window.matchMedia('(pointer: fine)').matches) first.focus();
  }

  function closeDialog(dialog) {
    if (!dialog) return;
    if (dialog.open && typeof dialog.close === 'function') dialog.close();
    else dialog.removeAttribute('open');
  }

  document.addEventListener('click', function (e) {
    var openBtn = e.target.closest('[data-dialog-open]');
    if (openBtn) {
      e.preventDefault();
      openDialog(document.getElementById(openBtn.getAttribute('data-dialog-open')), openBtn);
      return;
    }
    var closeBtn = e.target.closest('[data-dialog-close]');
    if (closeBtn) { closeDialog(closeBtn.closest('dialog')); return; }
    // Click on the backdrop (outside the dialog box) closes it
    if (e.target.tagName === 'DIALOG' && e.target.open) {
      var r = e.target.getBoundingClientRect();
      var inside = e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom;
      if (!inside) closeDialog(e.target);
    }
  });

  document.querySelectorAll('dialog').forEach(function (dialog) {
    dialog.addEventListener('close', function () {
      document.documentElement.classList.remove('has-dialog');
      resetForms(dialog);
      if (opener && typeof opener.focus === 'function') opener.focus();
      opener = null;
    });
  });

  /* ---------- Google Forms (post into hidden iframe, then say thanks) ---------- */
  function resetForms(scope) {
    var panel = scope.querySelector('[data-form-panel]');
    var thanks = scope.querySelector('[data-form-thanks]');
    if (thanks && !thanks.hidden) {
      thanks.hidden = true;
      if (panel) panel.hidden = false;
      var form = scope.querySelector('form[data-google-form]');
      if (form) { form.hidden = false; form.reset(); }
    }
  }

  document.querySelectorAll('form[data-google-form]').forEach(function (form) {
    form.addEventListener('submit', function () {
      // Let the browser post the form into the hidden iframe, then swap the UI.
      setTimeout(function () {
        var scope = form.closest('dialog') || form.parentNode;
        var panel = scope.querySelector('[data-form-panel]');
        var thanks = scope.querySelector('[data-form-thanks]');
        if (panel && thanks && !panel.contains(thanks)) panel.hidden = true;
        else form.hidden = true;
        if (thanks) {
          thanks.hidden = false;
          var again = thanks.querySelector('[data-form-again]');
          (again || thanks).focus && (again || thanks).focus();
        }
      }, 400);
    });
  });

  document.addEventListener('click', function (e) {
    var again = e.target.closest('[data-form-again]');
    if (again) resetForms(again.closest('dialog') || document);
  });

  /* ---------- "Add to calendar" menus ---------- */
  var menus = document.querySelectorAll('details[data-cal-menu]');
  function closeMenus(except) {
    menus.forEach(function (d) { if (d !== except) d.open = false; });
  }
  if (menus.length) {
    document.addEventListener('click', function (e) {
      var inMenu = e.target.closest('details[data-cal-menu]');
      if (!inMenu) closeMenus();
      else if (e.target.closest('a')) setTimeout(closeMenus, 0);
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') closeMenus();
    });
  }
})();
