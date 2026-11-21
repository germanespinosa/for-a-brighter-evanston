/**
 * For a Brighter Evanston: referendum pledge backend.
 *
 * A Google Apps Script bound to the "FABE Pledge" Google Sheet, deployed as a
 * web app (Execute as: me, Who has access: Anyone). The website talks to it:
 *
 *   GET  <web app URL>?action=count         -> {"ok":true,"count":123}
 *   POST <web app URL>  (body: JSON as text/plain, see doPost)
 *        -> {"ok":true,"count":124}                     new pledge stored
 *        -> {"ok":true,"already":true,"count":124}      email already pledged
 *        -> {"ok":false,"error":"invalid"|"busy"|"error"}
 *
 * Secrets never live in this file or in the website. Set them in
 * Project Settings > Script properties:
 *   MAILCHIMP_API_KEY   e.g. abc123...-us21   (optional; without it nobody is added to Mailchimp)
 *   MAILCHIMP_LIST_ID   the audience ID        (optional, needed with the key)
 *   TURNSTILE_SECRET    Cloudflare Turnstile secret key (optional; when set, every pledge must pass it)
 *
 * Sheet tabs (created automatically on first use):
 *   Signatures  one row per unique email: what the counter counts
 *   Rejected    spam and invalid submissions, for the team to review (never counted)
 * The campaign team views and exports the list from the Sheet itself
 * (File > Download > CSV).
 */

var SIGNATURES = 'Signatures';
var REJECTED = 'Rejected';
var HEADERS = ['Timestamp', 'First name', 'Last name', 'Email', 'Updates opt-in', 'Language', 'Source', 'Mailchimp'];
var REJECT_HEADERS = ['Timestamp', 'Reason', 'First name', 'Last name', 'Email', 'Language', 'Source'];
var COUNT_CACHE_SECONDS = 30;
var MIN_FILL_MS = 2500;          // faster than this is treated as a bot
var MAX_PER_MINUTE = 60;         // all submissions together, across every site
var MAX_PER_EMAIL_PER_HOUR = 5;  // repeated attempts with the same email

// ---------------------------------------------------------------- entry points

function doGet(e) {
  var action = e && e.parameter && e.parameter.action;
  if (action === 'count') {
    return json_({ ok: true, count: getCount_() });
  }
  return json_({ ok: true, service: 'fabe-pledge' });
}

function doPost(e) {
  var data;
  try {
    data = JSON.parse((e && e.postData && e.postData.contents) || '{}');
  } catch (err) {
    return json_({ ok: false, error: 'invalid' });
  }
  return json_(handlePledge_(data));
}

// ---------------------------------------------------------------- core logic

function handlePledge_(data) {
  var p = clean_(data);
  var cache = CacheService.getScriptCache();

  // Bots: hidden field filled in, or the form was submitted implausibly fast.
  // They get a normal-looking answer, and nothing is counted.
  if (p.honeypot) {
    reject_('honeypot', p);
    return { ok: true, count: getCount_() };
  }
  if (p.elapsed !== null && p.elapsed < MIN_FILL_MS) {
    reject_('too fast', p);
    return { ok: true, count: getCount_() };
  }

  if (!p.first || !p.last || !validEmail_(p.email)) {
    return { ok: false, error: 'invalid' };
  }

  // Overall rate limit (Apps Script cannot see visitors' IP addresses).
  var minuteKey = 'rate:' + Math.floor(Date.now() / 60000);
  var perMinute = Number(cache.get(minuteKey) || 0);
  if (perMinute >= MAX_PER_MINUTE) {
    reject_('rate limit', p);
    return { ok: false, error: 'busy' };
  }
  cache.put(minuteKey, String(perMinute + 1), 120);

  var emailKey = 'email:' + hash_(p.email);
  var attempts = Number(cache.get(emailKey) || 0);
  if (attempts >= MAX_PER_EMAIL_PER_HOUR) {
    reject_('repeated attempts', p);
    return { ok: false, error: 'busy' };
  }
  cache.put(emailKey, String(attempts + 1), 3600);

  var secret = prop_('TURNSTILE_SECRET');
  if (secret && !turnstileOk_(secret, p.turnstile)) {
    reject_('challenge failed', p);
    return { ok: false, error: 'invalid' };
  }

  var lock = LockService.getScriptLock();
  if (!lock.tryLock(20000)) return { ok: false, error: 'busy' };
  var row;
  try {
    var sheet = sheet_(SIGNATURES, HEADERS);
    if (emailRow_(sheet, p.email) > 0) {
      return { ok: true, already: true, count: countRows_(sheet) };
    }
    sheet.appendRow([new Date(), p.first, p.last, p.email, p.optin ? 'yes' : 'no', p.lang, p.source, '']);
    row = sheet.getLastRow();
    cache.remove('count');
  } finally {
    lock.releaseLock();
  }

  var count = getCount_();
  if (p.optin) {
    var status = addToMailchimp_(p);
    try {
      sheet_(SIGNATURES, HEADERS).getRange(row, HEADERS.indexOf('Mailchimp') + 1).setValue(status);
    } catch (err) { /* the pledge is already stored */ }
  }
  return { ok: true, count: count };
}

function getCount_() {
  var cache = CacheService.getScriptCache();
  var cached = cache.get('count');
  if (cached !== null) return Number(cached);
  var count = countRows_(sheet_(SIGNATURES, HEADERS));
  cache.put('count', String(count), COUNT_CACHE_SECONDS);
  return count;
}

// ---------------------------------------------------------------- helpers

function clean_(d) {
  d = d || {};
  var text = function (v, max) { return String(v === undefined || v === null ? '' : v).replace(/\s+/g, ' ').trim().slice(0, max); };
  var lang = text(d.lang, 2).toLowerCase() === 'es' ? 'es' : 'en';
  var source = text(d.source, 40).toLowerCase().replace(/[^a-z0-9_-]/g, '') || 'unknown';
  var elapsed = Number(d.elapsed);
  return {
    first: stripFormula_(text(d.first, 80)),
    last: stripFormula_(text(d.last, 80)),
    email: text(d.email, 254).toLowerCase(),
    optin: d.optin === true || d.optin === 'true' || d.optin === 'yes',
    lang: lang,
    source: source,
    honeypot: text(d.website, 200),
    elapsed: isFinite(elapsed) && d.elapsed !== undefined && d.elapsed !== null && d.elapsed !== '' ? elapsed : null,
    turnstile: text(d.turnstile, 4096)
  };
}

// A value starting with = + - @ would be treated as a formula by Sheets.
function stripFormula_(s) {
  return s.replace(/^[=+\-@]+/, '').trim();
}

function validEmail_(email) {
  return email.length <= 254 && /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email);
}

function sheet_(name, headers) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName(name);
  if (!sh) {
    sh = ss.insertSheet(name);
    sh.appendRow(headers);
    sh.setFrozenRows(1);
  }
  return sh;
}

function countRows_(sheet) {
  return Math.max(0, sheet.getLastRow() - 1);
}

function emailRow_(sheet, email) {
  var n = sheet.getLastRow() - 1;
  if (n < 1) return 0;
  var col = HEADERS.indexOf('Email') + 1;
  var values = sheet.getRange(2, col, n, 1).getValues();
  for (var i = 0; i < values.length; i++) {
    if (String(values[i][0]).trim().toLowerCase() === email) return i + 2;
  }
  return 0;
}

function reject_(reason, p) {
  try {
    sheet_(REJECTED, REJECT_HEADERS).appendRow([new Date(), reason, p.first, p.last, p.email, p.lang, p.source]);
  } catch (err) { /* logging must never break the response */ }
}

function prop_(name) {
  return PropertiesService.getScriptProperties().getProperty(name) || '';
}

function hash_(s) {
  var bytes = Utilities.computeDigest(Utilities.DigestAlgorithm.MD5, s, Utilities.Charset.UTF_8);
  return bytes.map(function (b) { return ('0' + (b & 0xff).toString(16)).slice(-2); }).join('');
}

function turnstileOk_(secret, token) {
  if (!token) return false;
  try {
    var res = UrlFetchApp.fetch('https://challenges.cloudflare.com/turnstile/v0/siteverify', {
      method: 'post',
      payload: { secret: secret, response: token },
      muteHttpExceptions: true
    });
    return JSON.parse(res.getContentText()).success === true;
  } catch (err) {
    return false;
  }
}

// Adds or updates the person in the Mailchimp audience, with the Pledge tag and
// a language tag. Returns a short status for the Sheet; never throws.
function addToMailchimp_(p) {
  var key = prop_('MAILCHIMP_API_KEY');
  var list = prop_('MAILCHIMP_LIST_ID');
  // Without a key, the website signs the person up from their browser
  // through the public Mailchimp signup form (see assets/js/pledge.js).
  if (!key || !list) return 'website signup form';
  var dc = key.split('-')[1];
  if (!dc) return 'bad key';
  var base = 'https://' + dc + '.api.mailchimp.com/3.0/lists/' + list + '/members/' + hash_(p.email);
  var headers = { Authorization: 'Basic ' + Utilities.base64Encode('fabe:' + key) };
  try {
    var put = UrlFetchApp.fetch(base, {
      method: 'put',
      contentType: 'application/json',
      headers: headers,
      muteHttpExceptions: true,
      payload: JSON.stringify({
        email_address: p.email,
        status_if_new: 'subscribed',
        merge_fields: { FNAME: p.first, LNAME: p.last }
      })
    });
    if (put.getResponseCode() >= 300) return 'error ' + put.getResponseCode();
    var tags = UrlFetchApp.fetch(base + '/tags', {
      method: 'post',
      contentType: 'application/json',
      headers: headers,
      muteHttpExceptions: true,
      payload: JSON.stringify({ tags: [{ name: 'Pledge', status: 'active' }, { name: p.lang.toUpperCase(), status: 'active' }] })
    });
    return tags.getResponseCode() < 300 ? 'added' : 'added, tags failed';
  } catch (err) {
    return 'error';
  }
}

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

// ---------------------------------------------------------------- team tools

/** Run from the editor before launch: deletes every pledge and resets the counter to zero. */
function resetAllPledges() {
  var sheet = sheet_(SIGNATURES, HEADERS);
  if (sheet.getLastRow() > 1) sheet.deleteRows(2, sheet.getLastRow() - 1);
  CacheService.getScriptCache().remove('count');
}
