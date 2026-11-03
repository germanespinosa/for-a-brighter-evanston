# Fabian: add a news article from a URL

**Who this is for:** Fabian, the Hermes agent that maintains the For A Brighter Evanston website.
**Job:** a user sends one article URL. You add it, in English and Spanish, to the site's **In the news** page, publish the change, confirm it is live, and reply to the user.

You touch exactly one file: `data/news.json`. Never edit anything else in the repository for this job.

---

## 0. Facts you need

| | |
|---|---|
| Repository | `germanespinosa/for-a-brighter-evanston`, branch `main` |
| File | `data/news.json`, an object with `_readme` and an `articles` list |
| Helper script | `scripts/news_tool.py` (Python 3, standard library only) |
| Live English page | https://germanespinosa.github.io/for-a-brighter-evanston/home/in-the-news/ |
| Live Spanish page | https://germanespinosa.github.io/for-a-brighter-evanston/es/noticias/ |
| Live data file | https://germanespinosa.github.io/for-a-brighter-evanston/data/news.json |
| Publishing | Every commit pushed to `main` goes live through GitHub Pages, usually in 1–2 minutes. Browsers may keep an older copy of the page; the news file itself is cached for up to 10 minutes. |

If the site later moves to `www.forabrighterevanston.org`, the live addresses become `https://www.forabrighterevanston.org/home/in-the-news/`, `/es/noticias/` and `/data/news.json`. Use whichever address the `url` line in `_config.yml` names.

### The entry you produce

```json
{
  "date": "2026-11-05",
  "source": "Evanston RoundTable",
  "site": "Evanston RoundTable",
  "url": "https://evanstonroundtable.com/2026/11/05/example-headline/",
  "title": "Headline exactly as the outlet published it",
  "summary": "One or two plain sentences, in your own words, on what the article reports.",
  "title_es": "El titular traducido al español",
  "summary_es": "El resumen traducido al español."
}
```

| Field | Required | Rule |
|---|---|---|
| `date` | yes | The article's **publication date** in `YYYY-MM-DD`. Not today's date, and not the "updated" date unless no publication date exists. |
| `source` | yes | The outlet's name. Reuse an existing spelling when the outlet is already listed (table below). |
| `site` | no | Name shown in the "Read on …" link. Use the same value as `source`. |
| `url` | yes | The article's canonical address (see step 2). |
| `title` | yes | The headline **word for word**. Keep the outlet's capitalization and punctuation; use curly apostrophes (’) when the outlet does. Do not shorten or rewrite it. |
| `summary` | strongly expected | 1–2 sentences, about 25–45 words, **your own words**. See the writing rules in step 4. |
| `title_es` | strongly expected | Spanish translation of the headline. |
| `summary_es` | strongly expected | Spanish translation of the summary. |
| `alt_url`, `alt_label`, `alt_label_es` | only for paywalls | A free legal copy of the same article (for example a Yahoo News syndication), with labels `"Read free on Yahoo"` / `"Leer gratis en Yahoo"`. |

Source names already in use; match these exactly:

`ABC7 Chicago` · `Axios Chicago` · `CBS Chicago` · `Chicago Sun-Times` · `Chicago Tribune` · `Evanston Now` · `Evanston RoundTable` · `FOIA Gras` · `FOX 32 Chicago` · `People Magazine` · `The Daily Northwestern` · `WTTW`

For a new outlet, use the name the outlet uses for itself on its own site (for example "Patch", "Block Club Chicago", "NBC Chicago").

---

## 1. Get a fresh copy of the repository

```bash
git clone https://github.com/germanespinosa/for-a-brighter-evanston.git   # first time only
cd for-a-brighter-evanston
git checkout main
git pull --ff-only origin main
python3 scripts/news_tool.py check
```

- `check` prints `OK: N articles`. Remember N.
- **If `check` reports problems before you have changed anything**, someone else broke the file. Stop and send the user **Message F** (section 7). Do not fix other people's entries without permission.
- If `git pull` fails, see **Publishing problems** (section 6).

---

## 2. Clean up the URL and check for duplicates

1. If the user's message has several URLs, do this whole procedure once per URL, in order, one commit each. If it has none, send **Message A**.
2. Follow redirects to the final article address. If it is a Google News, Apple News, Facebook, X or newsletter link, open it and use the outlet's own article address instead.
3. Prefer the page's canonical address (`<link rel="canonical">` or `og:url`) when it points at the same article.
4. Remove tracking parameters (`utm_…`, `fbclid`, `gclid`, `mc_cid`, `mc_eid`, `igshid`, `smid`, `cmpid`, `ref_src`) and anything after `#`. The helper script also does this when it adds the entry.
5. Check for a duplicate:

   ```bash
   python3 scripts/news_tool.py find "<clean url>"
   ```

   - `FOUND …`: the article is already listed. Do not add it again. Send **Message D** and stop.
   - `NOT FOUND`: continue.

---

## 3. Collect the information

Open the article and record, **from the page itself**:

- headline,
- publication date,
- outlet name,
- what the article actually reports (enough to write two sentences).

Where to look, in this order, if the page text is hard to read:

1. The visible headline, byline and dateline on the page.
2. Structured data: `<script type="application/ld+json">` (`headline`, `datePublished`, `publisher.name`).
3. Meta tags: `og:title`, `og:description`, `og:site_name`, `article:published_time`, `<meta name="description">`.
4. A date in the URL path (for example `/2026/10/28/`). Use it only when it agrees with the page, or as the last resort with the user's confirmation.

**Never invent or guess a headline, a date, a quote or a fact.** If something cannot be found, follow the recovery steps.

### Recovery when you cannot get the information

Try these in order. Stop as soon as you have a reliable headline, date and enough content for a summary.

| Situation | What to do |
|---|---|
| Timeout, 5xx error, "connection reset" | Wait 30 seconds and retry, at most 3 attempts in total. |
| 403 / bot check / CAPTCHA | Do not try to get around it. Use the meta tags and structured data if they were returned. Otherwise search the web for the exact URL or headline to find the outlet's own listing (search snippet, outlet's section page, RSS feed). |
| Paywall | Headline, date and the description in the meta tags are usually still readable; write the summary from those only. Search for a free syndicated copy of the same article (Yahoo News, MSN, AP); if you find one, add it as `alt_url`. Never copy paywalled text. |
| Page loads but the date is missing or ambiguous | Use `datePublished` or `article:published_time`. If two dates disagree, take the publication date, not the update date. If there is still no date, send **Message B** and wait. |
| Only the headline is available, nothing to summarize | Send **Message C**. Wait for the user's choice. |
| 404 / page removed | Search the outlet's site and the web for the headline. If you find the article at a new address, use that address and mention the change in your reply. If you cannot, send **Message A** (with the reason) and stop. |
| Not about D65 | The page is for coverage of Evanston/Skokie District 65: school closures, budget, boundaries, childcare and early-childhood programs, the board, the superintendent search, and community responses. If the article is clearly about something else, send **Message E** and wait. |
| Article is not in English | Keep `title` in the original language, write `summary` in English, and also fill `title_es` / `summary_es`. Mention it in your reply. |

If the user answers with the missing facts (for example "the date is Nov 5"), use their answer, then continue from step 4. In the commit message, record which fields came from the user.

---

## 4. Write the English and Spanish text

### English summary
- 1–2 sentences, about 25–45 words, plain and factual.
- Say what the article reports: who did what, what was decided, what the numbers are. Attribute claims to the article or the people in it ("Parents argue…", "The district says…").
- Write it in your own words. Do not copy sentences from the article. If you must quote, keep it under 15 words and in quotation marks; it is usually better not to quote at all.
- Keep the campaign's opinions out of the summary. The page describes coverage; it does not argue.
- Match the house style of existing entries: "D65" or "District 65", "Dewey and Lincolnwood", "$17 million", "the board".

### Spanish title and summary
- Translate faithfully; do not add or drop facts.
- Proper names stay as they are: Dewey, Lincolnwood, Evanston, Skokie, SACC, Head Start, TWI. "District 65" becomes "Distrito 65"; "D65" stays "D65"; "board" becomes "la junta".
- Write numbers and money the way existing entries do: `$17 millones`, `20 millones de dólares`, `9 de noviembre`.
- Use neutral Latin American Spanish with standard sentence capitalization (only the first word and proper nouns capitalized), even when the English headline is in Title Case.
- Re-read the Spanish once against the English before saving.

If you cannot produce a reliable Spanish version, add the entry without `title_es` / `summary_es` (the Spanish page will show English) and say so in your reply. Do not hold the article back for this.

---

## 5. Add, check, commit and publish

1. Write the entry to a temporary file **outside** the repository, for example `/tmp/news-entry.json`, containing only the one object shown in section 0.
2. Add it:

   ```bash
   python3 scripts/news_tool.py add /tmp/news-entry.json
   ```

   - `ADDED … OK: N+1 articles`: continue.
   - `DUPLICATE …`: send **Message D** and stop.
   - `NOT SAVED. PROBLEMS: …`: fix your entry file (wrong date format, missing field, etc.) and run `add` again. Nothing was written.
3. Confirm only one file changed and the diff is just your entry:

   ```bash
   python3 scripts/news_tool.py check
   git status --short          # expect only:  M data/news.json
   git diff --stat             # one file, roughly 10 lines added
   ```

   If anything else changed, run `git checkout -- .`, then repeat from step 1 of this section.
4. Commit with a descriptive message (format below), then push:

   ```bash
   git add data/news.json
   git commit -F /tmp/news-commit-message.txt
   git push origin main
   ```

### Commit message format

The first line is a summary, then a blank line, then the details. Keep the first line under about 72 characters; shorten the headline with "…" if needed.

```
News: add <Source> – <Headline> (<YYYY-MM-DD>)

Adds one article to the In the news page (data/news.json).

URL: <clean url>
Source: <source>
Published: <YYYY-MM-DD> (from <where the date came from, e.g. page dateline / datePublished / user>)
Spanish title and summary: included | not included (<reason>)
Free copy (alt_url): <url> | none
Information from: <article page | meta tags only (paywall) | search listing | user-provided: date>
Requested by: <user name> on <channel>, <date>

Added by Fabian (Hermes agent) following docs/agents/fabian-add-news-article.md
```

Example:

```
News: add Evanston RoundTable – District 65 parents threaten lawsuit… (2026-10-30)

Adds one article to the In the news page (data/news.json).

URL: https://evanstonroundtable.com/2026/10/30/district-65-parents-threaten-lawsuit/
Source: Evanston RoundTable
Published: 2026-10-30 (from page dateline)
Spanish title and summary: included
Free copy (alt_url): none
Information from: article page
Requested by: German on Telegram, 2026-10-31

Added by Fabian (Hermes agent) following docs/agents/fabian-add-news-article.md
```

5. Confirm it is live. Poll the live data file about every 30 seconds, for up to 10 minutes, until it contains your URL:

   ```bash
   curl -s "https://germanespinosa.github.io/for-a-brighter-evanston/data/news.json?nocache=$(date +%s)" | grep -F "<clean url>"
   ```

   When it appears, send **the final reply** (section 8). If it does not appear within 10 minutes, see section 6.

---

## 6. Publishing problems

| Problem | What to do |
|---|---|
| `git pull` or `git push` rejected because the remote has new commits | Run `git pull --rebase origin main`, then `python3 scripts/news_tool.py check`, then push again. |
| Rebase conflict in `data/news.json` | Run `git rebase --abort`, then `git fetch origin && git reset --hard origin/main` (this throws away only your local, unpushed edit). Repeat section 5 from the start; the duplicate check will catch it if someone already added the same article. |
| Push fails twice more after rebasing | Stop and send **Message G**. Include the error text. |
| Authentication or permission error (401/403, "permission denied", "could not read Username") | Do not retry with other credentials. Send **Message G**. |
| Any hint to force-push | Never use `git push --force` or `--force-with-lease` on `main`. |
| Pushed, but not live after 10 minutes | Check the build: `gh run list --repo germanespinosa/for-a-brighter-evanston --limit 3` (look for "pages build and deployment"), or the Actions tab on github.com. Still building: wait another 5 minutes and check again. Failed: send **Message H** with the run link. Succeeded but your URL is missing: re-run the `curl` check from section 5 without cache, and if it is still missing send **Message H**. |
| After the push, `check` fails or the live page shows "The articles couldn't load" | You published a broken file. Immediately run `git revert --no-edit HEAD` and `git push origin main`, confirm the live page lists articles again, then send **Message H**. |

---

## 7. Messages to the user when something blocks you

Send these in the same channel the request came from, one at a time. Fill in the brackets. After sending one, **wait for the user's answer** before you change anything; if there is no answer, do nothing further.

**A. Can't open the link**
> I couldn't open that link ([reason: page not found / blocked / no URL in your message]). I also searched for the article by its address [and headline] and didn't find it. Could you send me the headline and the date it was published, or another link to the same story?

**B. No publication date**
> I found the article "[headline]" ([source]), but the page doesn't show when it was published. What date should I list it under? (If you're not sure, I can use [date from the URL / the date you sent it]; just tell me that's OK.)

**C. Not enough to summarize** (paywall or headline only)
> I could read the headline ("[headline]", [source], [date]) but not the article itself, so I can't write a fair summary. Would you like me to:
> 1. add it with the headline only,
> 2. add it with a summary you send me (one or two sentences), or
> 3. skip it?

**D. Already listed**
> That article is already on the In the news page: "[title]" ([source], [date]). I didn't add it again. Want me to change anything in that entry?

**E. Possibly off-topic**
> "[headline]" ([source]) doesn't seem to be about District 65's closures, budget or boundaries ([one-line reason]). Should I still add it to the In the news page?

**F. The news file is already broken**
> The news list file on the site has an error I didn't make: [first problem reported by the check]. I haven't added your article yet. Should I fix the error, or would you rather look at it first?

**G. Couldn't publish**
> I prepared the entry for "[headline]" but couldn't publish it: [short error description]. Nothing on the site changed. [Here is the entry, ready to paste into data/news.json: …] Let me know when access is fixed and I'll try again.

**H. Published, but the site isn't showing it / something went wrong**
> I added "[headline]" to the news list, but [the site hasn't updated after 10 minutes / the site build failed: link / the update broke the news list, so I undid it]. [What you did.] Want me to try again?

---

## 8. Final reply when the article is live

Send this once the live check in section 5 succeeds:

> Added to In the news: **[title]** ([source], [Mon D, YYYY]).
> English: https://germanespinosa.github.io/for-a-brighter-evanston/home/in-the-news/
> Spanish: https://germanespinosa.github.io/for-a-brighter-evanston/es/noticias/
> If you don't see it yet, refresh the page (on a computer, Ctrl+Shift+R, or Cmd+Shift+R on a Mac; on a phone, pull down to reload). It can take a few minutes to show up everywhere.

Add one line only when it applies:
- "The Spanish page shows it in English for now; I couldn't translate it reliably."
- "I used the date you gave me ([date])."
- "The link you sent redirected, so I used the outlet's own address: [url]."
- "It's behind a paywall, so I added a free copy from [Yahoo News] as a second link."

---

## 9. Checklist

- [ ] Fresh `git pull` and a clean `check` before starting
- [ ] Clean canonical URL, no tracking parameters, not a duplicate
- [ ] Headline word for word; publication date verified (or confirmed by the user)
- [ ] Summary 1–2 sentences, own words, factual, no long quotes
- [ ] Spanish title and summary faithful to the English
- [ ] Added with `scripts/news_tool.py add`; `check` passes; only `data/news.json` changed
- [ ] Descriptive commit message in the required format
- [ ] Pushed to `main` without force; live file contains the URL
- [ ] Final reply sent with both links and the refresh note
