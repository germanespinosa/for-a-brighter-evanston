# Referendum pledge backend (Google Sheet + Apps Script)

The pledge pages on the website (`/pledge/`, `/es/compromiso/`, `/pledge-embed/`,
`/pledge-counter/` and the home page counter) store signatures and read the
live count through this script. It runs in a Google account the campaign
controls and writes to a Google Sheet in that account. No keys or passwords
are in this repository or on the website.

## One-time setup (about 10 minutes)

Use the campaign's Google account (the one the team should own the data with).

1. **Create the Sheet.** In Google Drive, create a new Google Sheet named
   `FABE Pledge`. Leave it empty; the script adds the `Signatures` and
   `Rejected` tabs itself.
2. **Add the script.** In the Sheet: Extensions > Apps Script. Delete what is
   in `Code.gs` and paste the whole content of [`Code.gs`](Code.gs) from this folder.
3. **Set the manifest.** In Apps Script: Project Settings (gear icon) > check
   "Show appsscript.json manifest file in editor". Back in the Editor, open
   `appsscript.json` and replace it with [`appsscript.json`](appsscript.json).
   Save.
4. **Deploy.** Deploy > New deployment > type **Web app**.
   - Execute as: **Me**
   - Who has access: **Anyone**

   Click Deploy and approve the permissions it asks for (it needs this
   spreadsheet and outside requests, for Mailchimp). Copy the **Web app URL**
   (it ends in `/exec`).
5. **Connect the website.** Put that URL in `_data/pledge.yml` as `endpoint:`
   (or send it to whoever maintains the site). The URL is not secret: it is
   visible to every visitor, like any form address.

## Mailchimp (the "Send me campaign updates" box)

This already works without any setup: when someone checks the box, their
browser signs them up through the same public Mailchimp signup form as the
site's "Get updates" box, with the same tag (settings in `_data/pledge.yml`,
`mailchimp:`). The Sheet's `Mailchimp` column then says `not configured`,
which only means the script itself did not contact Mailchimp.

To also tag pledgers `Pledge` and `EN`/`ES`: create those tags in Mailchimp,
then add their numeric IDs to `tags`, `tags_en` and `tags_es` in
`_data/pledge.yml`.

### Optional: script-side Mailchimp with an API key


In Apps Script: Project Settings > Script properties > Add script property:

| Property | Value |
| --- | --- |
| `MAILCHIMP_API_KEY` | A Mailchimp API key (Profile > Extras > API keys). It ends in `-usNN`. |
| `MAILCHIMP_LIST_ID` | The audience ID (Audience > Settings > Audience name and defaults). |

Only people who check the box are added, with the tag `Pledge` and `EN` or
`ES`. Until both properties are set, pledges are still stored and counted;
the `Mailchimp` column shows `not configured`.

## Spam protection

Built in: a hidden field bots fill in, a minimum time to fill the form, a limit
of 60 pledges a minute across all sites, and 5 attempts an hour per email.
Rejected submissions go to the `Rejected` tab and are never counted.
Apps Script cannot see visitors' IP addresses, so there is no per-IP limit.

Optional extra layer, Cloudflare Turnstile (free, needs a Cloudflare account):
create a widget for `forabrighterevanston.org`, put its **site key** in
`_data/pledge.yml` as `turnstile_sitekey:`, and its **secret key** in the script
property `TURNSTILE_SECRET`. Set both at the same time, or every pledge will
be refused.

## Day to day

- **See or export the list:** open the Sheet. File > Download > CSV.
- **The counter** is the number of rows in `Signatures` (one row per email).
  It refreshes about every 30 seconds.
- **Remove one pledge:** delete its row in `Signatures`.
- **Before launch:** in Apps Script, choose the function `resetAllPledges`
  and click Run. It deletes every test pledge so the counter starts at zero.
- **Changing the script later:** paste the new code, then Deploy > Manage
  deployments > edit (pencil) > Version: New version > Deploy. This keeps the
  same web app URL. A *new* deployment would get a different URL.

## Tests

`node apps-script/pledge/test/run-tests.js` runs `Code.gs` against stand-ins for
the Google services and checks storing, duplicates, spam rules, Mailchimp
opt-in and the reset.
