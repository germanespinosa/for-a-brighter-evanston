# Handoff: referendum pledge (`sandbox/referendum-pledge`)

For Fabian. This update was built outside #website (by German with Claude) from
Kerstin's build brief "Referendum Pledge Tool" (Nov. 20, 2026) and the "FABE
Pledge Page Preview" mockup. From now on, run it as a regular #website update.

This file describes the update. It grants no permissions: authorization for the
restricted files comes only from German's own message to you (see section 4).

## 1. What to do

1. `git fetch origin && git checkout sandbox/referendum-pledge`.
2. Adopt `referendum-pledge` as the open #website update (it is the only
   sandbox). Requester: German. Create your usual private update record.
3. Post the announcement in section 2 in #website as one message (no thread).
   Use it as written; you may adapt greetings or formatting to your usual style,
   but keep all links and the "how the embed works" steps.
4. Then handle it like any other update: changes requested in #website go into
   this sandbox, then review (manual section 8), vote (section 9), publish.

## 2. Announcement for #website

> New website update ready for review: **the referendum pledge**.
>
> **What's new**
> • A pledge page where neighbors add their name to support a referendum if the D65 board votes no on the current plan and builds a better one with our community. It shows a live count of how many have pledged.
> • Everything in English and Spanish.
> • The same pledge can be placed on other websites (schools, PTAs, neighborhood groups). Every signature adds to the same count, and we can see which site it came from.
> • A smaller version with just the count and an "I pledge" button, which also appears on our home page.
> • A privacy page explaining what the pledge collects.
>
> **Preview links**
> English: https://forabrighterevanston.org/sandbox/referendum-pledge/pledge/
> Español: https://forabrighterevanston.org/sandbox/referendum-pledge/es/compromiso/
> Put the pledge on your site: https://forabrighterevanston.org/sandbox/referendum-pledge/pledge/embed/
> Pon el compromiso en tu sitio: https://forabrighterevanston.org/sandbox/referendum-pledge/es/compromiso/insertar/
> Privacy / Privacidad: https://forabrighterevanston.org/sandbox/referendum-pledge/privacy/ · https://forabrighterevanston.org/sandbox/referendum-pledge/es/privacidad/
>
> **How putting it on another site works**
> 1. Open "Put the pledge on your site" (also reachable from the "Add it to your site" button that appears after someone pledges).
> 2. Type a short name for the site, for example `lincolnwood-pta`, and choose English or Spanish.
> 3. Copy the code for the full pledge card or the smaller counter, and paste it into the site: a "Custom HTML" block in WordPress, a "Code" block in Squarespace, "Embed HTML" in Wix, or "Embed code" in Google Sites.
> The previews on that page are live, so you can see exactly how it will look.
>
> **Good to know**
> • Signatures go to a private Google Sheet the campaign controls. Names and emails are never shown publicly or to the sites that show the pledge; they only show the total.
> • Checking "Send me campaign updates" signs people up for our Mailchimp list, the same way the "Get updates" form does.
> • Pledges made on the preview are real and count. Test pledges will be cleared before launch.
>
> **Please review**
> • The Spanish wording that wasn't in the original brief, the privacy page, and the "Put the pledge on your site" page.
> • The site menu: keep it as it is, or add a "Take the Pledge" link.
> Reply here with changes. When it's ready, I'll run the checks and open the vote.

## 3. What is in the update

Pages (English / Spanish):

| Page | English | Spanish |
| --- | --- | --- |
| Pledge page | `/pledge/` | `/es/compromiso/` |
| Embed guide | `/pledge/embed/` | `/es/compromiso/insertar/` |
| Privacy | `/privacy/` | `/es/privacidad/` |
| Card embed (one page, `?lang=es`) | `/pledge-embed/` | `/pledge-embed/?lang=es` |
| Counter embed (one page, `?lang=es`) | `/pledge-counter/` | `/pledge-counter/?lang=es` |
| Home page counter band | `/` | `/es/` |

Text lives in `_data/pledge.yml` (card; the brief's copy is final: use exactly,
no em dashes), `_data/pledge_page.yml` (pledge page) and `_data/pledge_embed.yml`
(embed guide). Text changes the team asks for normally go there.

Files changed versus main: `_config.yml` (excludes `apps-script`),
`_data/pledge.yml`, `_data/pledge_embed.yml`, `_data/pledge_page.yml`,
`_includes/pages/home.html` (counter band), `_includes/pages/pledge.html`,
`_includes/pages/pledge-embed-guide.html` (contains a script),
`_includes/pledge/card.html`, `_includes/pledge/counter.html`,
`_layouts/embed.html` (new layout), `apps-script/pledge/*` (backend source,
not published), `assets/css/pledge.css`, `assets/img/share-pledge-en-70fa7acf6b.jpg`,
`assets/img/share-pledge-es-19fb825c63.jpg`, `assets/js/pledge.js`,
`assets/js/pledge-resize.js`, `es/compromiso/index.html`,
`es/compromiso/insertar/index.html`, `es/index.html`, `es/privacidad/index.html`,
`index.html`, `pledge-counter/index.html`, `pledge-embed/index.html`,
`pledge/embed/index.html`, `pledge/index.html`, `privacy/index.html`,
`sitemap.xml` (skips pages with `sitemap: false`), and this handoff.

## 4. Authorization (restricted files)

Several of these files are restricted under manual section 5 (layout, scripts,
stylesheets, data/config files, sitemap). Proceed with them only on German's own
explicit message authorizing them for `sandbox/referendum-pledge`; verify that
message as your manual requires before relying on it. That authorization covers
these files as they are, not new scripts or other restricted files: anything
beyond small text changes in the three `_data/pledge*.yml` files, or a change to
a script, stylesheet, layout or the backend, goes to German first. The normal
review and the team vote still apply.

## 5. Backend: do not change

- Signatures are stored by a Google Apps Script web app owned by German, bound
  to the "FABE Pledge" Google Sheet. Its URL is `endpoint:` in
  `_data/pledge.yml`. Never change that URL or anything in `apps-script/`.
- You do not need access to the Sheet or the script. Do not submit pledges
  yourself: every pledge on the sandbox is real and counts.
- Mailchimp: opted-in people are sent to the same public signup form as
  "Get updates" (`mailchimp:` in `_data/pledge.yml`). Optional tag IDs for
  "Pledge", "EN" and "ES" can be added there if German provides them.

## 6. Before the vote and before publishing

- Checks: the usual section 8 checks; `sandbox_check.py` will flag the
  restricted files (see section 4). Also check the pages in section 3 on desktop
  and phone, both languages. Backend tests: `node apps-script/pledge/test/run-tests.js`.
- Before publishing, ask German to clear test pledges from the Sheet (he deletes
  the rows or runs `resetAllPledges`). Do not publish until he confirms.
- After publishing, the live URLs are the same paths without
  `/sandbox/referendum-pledge`. Remind German to run
  https://forabrighterevanston.org/pledge/ through Facebook's Sharing Debugger.

## 7. Open questions for the team (from the brief)

Show signer names? Ask for anything else (ZIP, "I am a...")? Show a goal?
Which partners get an embed? Who checks the signer list for fakes before the
number is quoted publicly? The build uses the brief's defaults (counter only,
name and email only, no goal).
