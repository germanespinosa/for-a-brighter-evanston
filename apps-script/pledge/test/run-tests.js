// Runs Code.gs in Node with small fakes of the Apps Script services.
// Usage: node apps-script/pledge/test/run-tests.js
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const crypto = require('crypto');
const assert = require('assert');

function makeEnv(props = {}) {
  const sheets = {};
  const cache = new Map();
  const fetches = [];
  let now = 1_800_000_000_000;
  class Sheet {
    constructor() { this.rows = []; }
    appendRow(r) { this.rows.push(r.slice()); }
    setFrozenRows() {}
    getLastRow() { return this.rows.length; }
    getRange(row, col, nRows = 1, nCols = 1) {
      const rows = this.rows;
      return {
        getValues: () => rows.slice(row - 1, row - 1 + nRows).map(r => r.slice(col - 1, col - 1 + nCols)),
        setValue: v => { rows[row - 1][col - 1] = v; },
      };
    }
    deleteRows(start, n) { this.rows.splice(start - 1, n); }
  }
  const ctx = {
    Date: class extends Date { constructor(...a) { super(...(a.length ? a : [now])); } static now() { return now; } },
    Math, JSON, Number, String, isFinite,
    SpreadsheetApp: { getActiveSpreadsheet: () => ({
      getSheetByName: n => sheets[n] || null,
      insertSheet: n => (sheets[n] = new Sheet()),
    }) },
    CacheService: { getScriptCache: () => ({
      get: k => (cache.has(k) ? cache.get(k) : null),
      put: (k, v) => cache.set(k, v),
      remove: k => cache.delete(k),
    }) },
    LockService: { getScriptLock: () => ({ tryLock: () => true, releaseLock: () => {} }) },
    PropertiesService: { getScriptProperties: () => ({ getProperty: k => (k in props ? props[k] : null) }) },
    Utilities: {
      DigestAlgorithm: { MD5: 'md5' }, Charset: { UTF_8: 'utf8' },
      computeDigest: (alg, s) => Array.from(crypto.createHash('md5').update(s, 'utf8').digest()).map(b => (b > 127 ? b - 256 : b)),
      base64Encode: s => Buffer.from(s).toString('base64'),
    },
    UrlFetchApp: { fetch: (url, opts) => {
      fetches.push({ url, opts });
      if (url.includes('turnstile')) return { getResponseCode: () => 200, getContentText: () => JSON.stringify({ success: opts.payload.response === 'good' }) };
      return { getResponseCode: () => 200, getContentText: () => '{}' };
    } },
    ContentService: { MimeType: { JSON: 'json' }, createTextOutput: t => ({ setMimeType: () => ({ text: t }) }) },
  };
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(path.join(__dirname, '..', 'Code.gs'), 'utf8'), ctx);
  const post = body => JSON.parse(ctx.doPost({ postData: { contents: typeof body === 'string' ? body : JSON.stringify(body) } }).text);
  const count = () => JSON.parse(ctx.doGet({ parameter: { action: 'count' } }).text);
  return { ctx, sheets, cache, fetches, post, count, tick: ms => { now += ms; } };
}

const ok = { first: 'Ana', last: 'Ruiz', email: 'Ana@Example.org ', optin: false, lang: 'en', source: 'fabe', website: '', elapsed: 9000 };
const tests = [];
const test = (name, fn) => tests.push([name, fn]);

test('count starts at zero and the sheet is created', () => {
  const env = makeEnv();
  assert.deepStrictEqual(env.count(), { ok: true, count: 0 });
  assert.ok(env.sheets.Signatures);
});

test('a valid pledge is stored with all fields and counted', () => {
  const env = makeEnv();
  const r = env.post(ok);
  assert.deepStrictEqual(r, { ok: true, count: 1 });
  const row = env.sheets.Signatures.rows[1];
  assert.strictEqual(row[1], 'Ana'); assert.strictEqual(row[2], 'Ruiz');
  assert.strictEqual(row[3], 'ana@example.org');
  assert.strictEqual(row[4], 'no'); assert.strictEqual(row[5], 'en'); assert.strictEqual(row[6], 'fabe');
  assert.ok(row[0] instanceof Date);
  assert.strictEqual(env.count().count, 1);
});

test('the same email (any case, spaces) is never counted twice', () => {
  const env = makeEnv();
  env.post(ok);
  const r = env.post({ ...ok, email: '  ANA@example.ORG' });
  assert.deepStrictEqual(r, { ok: true, already: true, count: 1 });
  assert.strictEqual(env.sheets.Signatures.rows.length, 2);
});

test('honeypot and too-fast submissions are not counted but are logged', () => {
  const env = makeEnv();
  assert.strictEqual(env.post({ ...ok, website: 'http://spam' }).count, 0);
  assert.strictEqual(env.post({ ...ok, email: 'b@x.org', elapsed: 400 }).count, 0);
  assert.strictEqual(env.count().count, 0);
  assert.strictEqual(env.sheets.Rejected.rows.length, 3);
});

test('missing names or a bad email are refused', () => {
  const env = makeEnv();
  assert.strictEqual(env.post({ ...ok, first: '' }).error, 'invalid');
  assert.strictEqual(env.post({ ...ok, email: 'not-an-email' }).error, 'invalid');
  assert.strictEqual(env.post('not json').error, 'invalid');
  assert.strictEqual(env.count().count, 0);
});

test('formula-like names are neutralised', () => {
  const env = makeEnv();
  env.post({ ...ok, first: '=HYPERLINK("x")', last: '+1' });
  const row = env.sheets.Signatures.rows[1];
  assert.ok(!/^[=+\-@]/.test(row[1]) && !/^[=+\-@]/.test(row[2]));
});

test('language and source are normalised', () => {
  const env = makeEnv();
  env.post({ ...ok, lang: 'ES', source: 'IINS<script>' });
  const row = env.sheets.Signatures.rows[1];
  assert.strictEqual(row[5], 'es'); assert.strictEqual(row[6], 'iinsscript');
});

test('without the box checked nobody is sent to Mailchimp', () => {
  const env = makeEnv({ MAILCHIMP_API_KEY: 'k-us21', MAILCHIMP_LIST_ID: 'L1' });
  env.post(ok);
  assert.strictEqual(env.fetches.length, 0);
});

test('with the box checked the person is added with Pledge and language tags', () => {
  const env = makeEnv({ MAILCHIMP_API_KEY: 'k-us21', MAILCHIMP_LIST_ID: 'L1' });
  env.post({ ...ok, optin: true, lang: 'es' });
  assert.strictEqual(env.fetches.length, 2);
  const md5 = crypto.createHash('md5').update('ana@example.org').digest('hex');
  assert.strictEqual(env.fetches[0].url, `https://us21.api.mailchimp.com/3.0/lists/L1/members/${md5}`);
  assert.strictEqual(JSON.parse(env.fetches[0].opts.payload).status_if_new, 'subscribed');
  assert.deepStrictEqual(JSON.parse(env.fetches[1].opts.payload).tags.map(t => t.name), ['Pledge', 'ES']);
  assert.strictEqual(env.sheets.Signatures.rows[1][7], 'added');
  assert.strictEqual(env.sheets.Signatures.rows[1][4], 'yes');
});

test('opt-in without Mailchimp configured still stores the pledge', () => {
  const env = makeEnv();
  assert.strictEqual(env.post({ ...ok, optin: true }).count, 1);
  assert.strictEqual(env.sheets.Signatures.rows[1][7], 'not configured');
});

test('with a Turnstile secret, a missing or bad token is refused', () => {
  const env = makeEnv({ TURNSTILE_SECRET: 's' });
  assert.strictEqual(env.post(ok).error, 'invalid');
  assert.strictEqual(env.post({ ...ok, turnstile: 'bad' }).error, 'invalid');
  assert.strictEqual(env.post({ ...ok, turnstile: 'good' }).count, 1);
});

test('the overall rate limit stops floods without counting them', () => {
  const env = makeEnv();
  for (let i = 0; i < 60; i++) env.post({ ...ok, email: `p${i}@x.org` });
  assert.strictEqual(env.post({ ...ok, email: 'late@x.org' }).error, 'busy');
  assert.strictEqual(env.count().count, 60);
  env.tick(61_000);
  assert.strictEqual(env.post({ ...ok, email: 'late@x.org' }).count, 61);
});

test('reset clears every pledge', () => {
  const env = makeEnv();
  env.post(ok); env.post({ ...ok, email: 'z@x.org' });
  env.ctx.resetAllPledges();
  assert.strictEqual(env.count().count, 0);
});

let failed = 0;
for (const [name, fn] of tests) {
  try { fn(); console.log('ok   ' + name); }
  catch (e) { failed++; console.log('FAIL ' + name + '\n     ' + e.message); }
}
console.log(`\n${tests.length - failed}/${tests.length} passed`);
process.exit(failed ? 1 : 0);
