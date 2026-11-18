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
    success: 'Mailchimp recibió su solicitud. Revise su correo por si necesita confirmar la inscripción.',
    rejected: 'Mailchimp no pudo completar la inscripción. Revise sus datos e inténtelo de nuevo.',
    uncertain: 'No pudimos confirmar el resultado. Antes de volver a intentarlo, revise su correo o contacte al equipo; es posible que Mailchimp haya recibido su solicitud.',
    captcha: 'Mailchimp necesita una verificación. La inscripción aún no está completa; continúe en Mailchimp.',
    unavailable: 'El formulario no está disponible aquí. Puede enviar sus datos directamente a Mailchimp en una pestaña nueva.',
    fallback: 'Enviar directamente a Mailchimp'
  } : {
    loading: 'Loading the Mailchimp form…',
    pending: 'Sending to Mailchimp…',
    success: 'Mailchimp received your request. Check your email in case you need to confirm your signup.',
    rejected: 'Mailchimp could not complete the signup. Check your details and try again.',
    uncertain: 'We could not confirm the result. Before trying again, check your email or contact the team; Mailchimp may have received your request.',
    captcha: 'Mailchimp requires verification. Signup is not complete; continue on Mailchimp.',
    unavailable: 'The form is unavailable here. You can send your details directly to Mailchimp in a new tab.',
    fallback: 'Send directly to Mailchimp'
  };
  var state = 'loading';
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
    if (state !== 'loading') return;
    var jq = window.jQuery;
    var mc = window.mc;
    if (!jq || !mc || !mc.ajaxOptions || !mc.mce_validator ||
        mc.ajaxOptions.url !== form.action.replace('/post?u=', '/post-json?u=') + '&c=?') {
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
      } else if (response && response.result === 'error' && response.msg === 'captcha' &&
                 response.params && typeof response.params === 'object') {
        var url = new URL(form.action);
        url.search = jq.param(response.params);
        captcha.href = url.href;
        captcha.hidden = false;
        state = 'captcha';
        status.textContent = words.captcha;
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
