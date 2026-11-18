/* Mailchimp's generated validator is loaded only after this guard is installed. */
(function () {
  'use strict';
  var form = document.querySelector('[data-mailchimp-form]');
  if (!form) return;
  var status = form.querySelector('[data-mailchimp-status]');
  var captcha = form.querySelector('[data-mailchimp-captcha]');
  var es = form.getAttribute('data-language') === 'es';
  var words = es ? {
    loading: 'Cargando el formulario de Mailchimp…',
    pending: 'Enviando a Mailchimp…',
    success: '¡Gracias por suscribirse!',
    rejected: 'Mailchimp no pudo completar la inscripción. Revise sus datos e inténtelo de nuevo.',
    uncertain: 'No pudimos confirmar el resultado. Antes de volver a intentarlo, revise su correo o contacte al equipo; es posible que Mailchimp haya recibido su solicitud.',
    captcha: 'Mailchimp solicitó una verificación. La inscripción no se ha completado; continúe en Mailchimp para intentarlo.',
    captchaInvalid: 'Mailchimp solicitó una verificación, pero no pudimos comprobar el enlace. ',
    unavailable: 'El formulario no está disponible aquí. Puede enviar sus datos directamente a Mailchimp en una pestaña nueva.',
    fallback: 'Enviar directamente a Mailchimp'
  } : {
    loading: 'Loading the Mailchimp form…',
    pending: 'Sending to Mailchimp…',
    success: 'Thanks for subscribing!',
    rejected: 'Mailchimp could not complete the signup. Check your details and try again.',
    uncertain: 'We could not confirm the result. Before trying again, check your email or contact the team; Mailchimp may have received your request.',
    captcha: 'Mailchimp requested verification. Your signup is not complete; continue on Mailchimp to proceed.',
    captchaInvalid: 'Mailchimp requested verification, but we could not verify the link. ',
    unavailable: 'The form is unavailable here. You can send your details directly to Mailchimp in a new tab.',
    fallback: 'Send directly to Mailchimp'
  };
  var state = 'loading';
  var hadMc = Object.prototype.hasOwnProperty.call(window, 'mc');
  var previousMc = window.mc;
  var hadJQuery = Object.prototype.hasOwnProperty.call(window, 'jQuery');
  var previousJQuery = window.jQuery;
  var hadDollar = Object.prototype.hasOwnProperty.call(window, '$');
  var previousDollar = window.$;
  var script = document.createElement('script');
  var loaderTimer;
  var fallback = document.createElement('button');
  fallback.type = 'button';
  fallback.className = 'btn btn--navy';
  fallback.textContent = words.fallback;
  fallback.hidden = true;
  status.after(fallback);
  status.textContent = words.loading;

  function unavailable() {
    if (state !== 'loading') return;
    state = 'unavailable';
    script.remove();
    status.textContent = words.unavailable;
    fallback.hidden = false;
  }

  /* The bundled validator predates destroy() and binds unnamespaced delegates.
     Remove only its own handlers, not other handlers on the same elements. */
  function cleanupVendor(jq, mc) {
    if (jq && jq !== previousJQuery && jq.fn) {
      var validator = (jq.data && jq.data(form, 'validator')) || (mc && mc.mce_validator);
      if (validator && typeof validator.destroy === 'function') validator.destroy();
      if (typeof jq._data === 'function') {
        [form, document].forEach(function (element) {
          var events = jq._data(element, 'events') || {};
          Object.keys(events).forEach(function (type) {
            events[type].slice().forEach(function (entry) {
              var source = Function.prototype.toString.call(entry.handler);
              var delegate = element === form && /var e=a\(c\.target\);return e\.is\(b\)\?d\.apply\(e,arguments\)/.test(source);
              var submit = element === form && type === 'submit' && /c\.settings\.submitHandler/.test(source) && /c\.focusInvalid/.test(source);
              var keydown = element === document && type === 'keydown' && /keycode\s*=/.test(source) && /mc\.showPopup/.test(source);
              if (delegate || submit || keydown) jq(element).off(type + (entry.namespace ? '.' + entry.namespace : ''), entry.handler);
            });
          });
        });
      }
      if (jq.removeData) jq.removeData(form, 'validator');
      if (typeof jq.noConflict === 'function') jq.noConflict(true);
    }
    if (hadJQuery) window.jQuery = previousJQuery;
    else delete window.jQuery;
    if (hadDollar) window.$ = previousDollar;
    else delete window.$;
    if (hadMc) window.mc = previousMc;
    else delete window.mc;
  }

  /* A confirmed submission can be followed by a new, deliberate signup. */
  document.addEventListener('click', function (event) {
    var opener = event.target.closest('[data-dialog-open="updates-dialog"]');
    if (opener && state === 'complete') {
      state = 'ready';
      status.textContent = '';
    }
  }, true);

  /* Stop native submission while loading or when a previous result is uncertain. */
  form.addEventListener('submit', function (event) {
    if (state !== 'ready' || !form.reportValidity()) {
      event.preventDefault();
      event.stopImmediatePropagation();
    }
  }, true);

  fallback.addEventListener('click', function () {
    if (state !== 'unavailable' || !form.reportValidity()) return;
    /* Native POST bypasses the validator and lets Mailchimp display its response. */
    state = 'uncertain';
    fallback.hidden = true;
    status.textContent = words.uncertain;
    HTMLFormElement.prototype.submit.call(form);
  });

  script.src = 'https://s3.amazonaws.com/downloads.mailchimp.com/js/mc-validate.js';
  script.onload = function () {
    clearTimeout(loaderTimer);
    var jq = window.jQuery;
    var mc = window.mc;
    if (state !== 'loading') {
      /* Removing a pending script does not guarantee it cannot execute later. */
      cleanupVendor(jq, mc);
      return;
    }
    if (!jq || jq === previousJQuery || typeof jq.noConflict !== 'function' ||
        typeof jq.param !== 'function' || !mc || !mc.ajaxOptions || !mc.mce_validator ||
        mc.ajaxOptions.url !== form.action.replace('/post?u=', '/post-json?u=') + '&c=?') {
      cleanupVendor(jq, mc);
      unavailable();
      return;
    }
    window.fnames = ['EMAIL', 'FNAME', 'LNAME'];
    window.ftypes = ['email', 'text', 'text'];
    jq.noConflict(true);
    mc.ajaxOptions.timeout = 8000;
    mc.ajaxOptions.beforeSend = function () {
      state = 'pending';
      captcha.hidden = true;
      status.textContent = words.pending;
    };
    /* Never pass provider messages to the vendor's HTML-rendering callback. */
    mc.ajaxOptions.success = function (response) {
      if (state !== 'pending') return;
      if (response && response.result === 'success') {
        state = 'complete';
        status.textContent = words.success;
        form.reset();
      } else if (response && response.result === 'error' && response.msg === 'captcha') {
        state = 'uncertain';
        /* Follow the vendor's algorithm, but only for the configured form URL
           and only after a visitor deliberately activates the link. */
        var params = response.params;
        var query = '';
        try {
          if (params && jq.isPlainObject(params) && Object.keys(params).length) query = jq.param(params);
          var action = new URL(form.action);
          if (query && action.origin === 'https://forabrighterevanston.us9.list-manage.com' &&
              action.pathname === '/subscribe/post' && !action.username && !action.password) {
            captcha.href = action.origin + action.pathname + '?' + query;
            captcha.target = '_blank';
            captcha.rel = 'noopener noreferrer';
            captcha.hidden = false;
            status.textContent = words.captcha;
          } else {
            status.textContent = words.captchaInvalid + words.uncertain;
          }
        } catch (error) {
          status.textContent = words.captchaInvalid + words.uncertain;
        }
      } else if (response && response.result === 'error') {
        state = 'ready';
        status.textContent = words.rejected;
      } else {
        state = 'uncertain';
        status.textContent = words.uncertain;
      }
    };
    mc.ajaxOptions.error = function () {
      if (state !== 'pending') return;
      state = 'uncertain';
      status.textContent = words.uncertain;
    };
    state = 'ready';
    status.textContent = '';
  };
  script.onerror = unavailable;
  loaderTimer = setTimeout(unavailable, 8000);
  document.head.appendChild(script);
})();
