# Working with Fabian
## Team help: news articles and website updates

For a Brighter Evanston • Team guide

Use Slack to request changes; you do not need to edit code or use GitHub. This guide summarizes the repository’s operating manuals, not a certification that every deployment setting or automation is active. The manuals linked at the end are the detailed source of truth.[1][2]

## Quick start

- **Get this guide:** send **`-help`** to Fabian. The latest PDF is kept in the GitHub repository at `docs/help/team-help.pdf`. This is a regular message, not the built-in `/help` command.

- **Add or remove a news article:** post in **#news**, mention **@fabian**, and wait for a preview. The requester or German must explicitly confirm before the change is published.[1]
- **Change website content:** post in **#website**, mention **@fabian**, and review the sandbox. Publication requires a review followed by **at least two yes votes and no no votes**, cast as messages to @fabian.[2]
- **Use top-level messages, never threads.** Keep follow-up answers and confirmations in the relevant channel and identify the article or sandbox when there could be confusion.[1][2]

# 1. Add or remove news articles

## Add an article

**Example request in #news**

> @fabian Please add this article to In the news: [paste the article’s link]

1. **Send the original article link.** Coverage should concern District 65—for example closures, finances, boundaries, childcare, early-childhood programs, board decisions or community responses.[1]
2. **Look for an acknowledgment.** Fabian should respond immediately, check whether the article is already listed, and read the source before preparing the preview.[1]
3. **Review the full preview.** It should show the original headline, an English summary, a Spanish title and summary, the outlet, publication date and article link. Any missing Spanish text or limitations in what Fabian could read should be disclosed.[1]
4. **Request corrections or approve.** For example: “Please change the summary to…” or “@fabian Yes, publish the RoundTable article about Dewey TWI.” A changed preview requires a fresh confirmation. Only the requester or German can confirm; silence is not approval.[1]
5. **Wait for the live confirmation.** After approval, Fabian validates and uploads the entry, checks that it appears on the live site, then posts the English and Spanish page links. Each article is handled separately.[1]

**Publication dates matter.** Fabian must take the original publication date from the article’s own dateline or publication metadata, in the outlet’s local time—not an update date, URL, search result or today’s date. If the date is unreadable or conflicting, Fabian asks you and waits. A date you provide is identified as user-provided; the full preview still needs approval.[1]

**Blocked or paywalled article?** Fabian may ask for the headline, publication date, another legal link or a summary you supply. If there is not enough content to summarize fairly, you may choose headline-only, provide a summary or skip the article. A duplicate will not be added again.[1]

## Remove an article

**Example requests in #news**

> @fabian Remove the article titled “[full or partial title].”

> @fabian Remove the WTTW article published on [date].

> @fabian Remove this article from In the news: [link]

1. **Identify the article** by link, title, or outlet and date; include a reason if useful.[1]
2. **Check Fabian’s match.** Fabian shows its full title, summary, source, date and link. If several articles match, choose the intended one; Fabian must still obtain explicit approval of the exact removal.[1]
3. **Confirm in #news.** For example: “@fabian Yes, remove [article title].” The requester or German must approve before removal.[1]
4. **Wait for verification.** Fabian removes the entry from both language versions and confirms after checking the live news list.[1]

To stop a pending addition or removal, say “cancel” or “stop.” To restore a removed article, request it in #news; restoring it requires an addition preview and confirmation.[1]

# 2. Request a website update

## Start or join a sandbox

**Example request in #website**

> @fabian I want to update the website. Please add an FAQ page using the text below, and offer a Spanish version. [paste text]

1. **Describe the change clearly.** Include the existing page link, the exact replacement text or desired outcome, and any images or PDFs.[2]
2. **Fabian acknowledges and prepares the sandbox.** This is a preview copy with a yellow banner, not the live site. Its link has the form https://forabrighterevanston.org/sandbox/<id>/ . Only one sandbox can be open at a time; further requests join the existing update.[2]
3. **Review the sandbox and request edits.** Anyone in #website can contribute, not just the original requester. Nothing in the sandbox is published to the live site merely because it looks finished.[2]
4. **Review both languages when available.** Spanish is encouraged but not mandatory for website updates. Fabian should offer a translation when English content changes without Spanish.[2]

The sandbox stays open until the group publishes or destroys it; inactivity alone does not close it. News remains managed through #news, and the sandbox is intended to show the current live news list.[2]

## What you can request

- New pages and changes to ordinary page content.[2]
- Supported text changes on built-in pages, such as home-page wording, next-meeting information and news-page labels.[2]
- Images in JPG, PNG, WebP or GIF format, and PDF documents up to 5 MB. Fabian should resize photos and strip location metadata before adding them.[2]

**Ask German about structural changes:** overall design, styling, templates, navigation-menu changes, site/build settings, scripts, forms or embeds, and deleting published pages. A new page can be linked from existing page text but cannot be added to the main menu through this workflow. The Write to the Board letter text is also outside the permitted content-editing workflow because it lives in a script.[2]

**Useful follow-ups in #website**

> @fabian What has changed in the sandbox?

> @fabian Replace the second paragraph on [page] with: [exact text]

> @fabian Add the Spanish version too.

> @fabian Undo the last change.

# 3. Review, vote and publish website changes

## Request publication

When the sandbox is ready, post: **“@fabian Publish [sandbox name]”** or **“@fabian Let’s vote on [sandbox name].”** This requests a review and vote; it does not bypass either step.[2]

Fabian brings the sandbox up to date, checks permitted changes, links, images and language coverage, and checks desktop and phone layouts. The review lists changes, blocking problems, suggestions, Spanish status, visual findings and Fabian’s recommendation. If a visual check cannot be completed, that limitation must be disclosed. Blocking problems must be fixed before voting.[2]

## Cast your vote

Fabian’s vote message includes a link to the updated site, a direct link to every changed page, and a short summary of each change, so anyone can review before voting.[2]

- **Vote by posting a message in #website:** “@fabian vote yes” or “@fabian vote no: [your reason]”. Reactions do not count; votes must be messages mentioning @fabian.[2]
- Short forms work too: “@fabian yes”, “@fabian ✅”, “@fabian no, [reason]”. To take a vote back: “@fabian withdraw my vote”. If your message is unclear, Fabian asks whether it’s a yes or a no.[2]
- Everyone in #website can vote, including the requester. Each person counts once, using their latest vote; bots do not count. Fabian replies to every vote with the running tally.[2]
- The update passes as soon as there are **two or more yes votes and zero no votes**. Any no vote blocks publication while it remains; please explain the concern so the group can address it.[2]
- The vote is open for **24 hours** from Fabian’s vote message. If it expires without passing, the sandbox remains, but publication needs a fresh review and vote.[2]
- The sandbox is **frozen during voting**. To change it, say “@fabian Cancel the vote on [sandbox name],” then request edits. A new review and vote are required afterward.[2]

Fabian recounts from the channel on every vote message, so a vote is never lost or counted twice. Votes after the 24-hour deadline don’t count. Fabian posts the closing message at the deadline if a scheduled check is set up, otherwise the next time anyone mentions him in #website. He doesn’t promise reminders he can’t schedule. The vote applies only to the reviewed version: if the sandbox changes, the old approvals cannot authorize publication of the new version.[2]

## After approval

Fabian publishes the approved update without changing the news list, verifies the changed live pages, removes the sandbox and posts the live links and approvers. A failed build or merge conflict must be reported—not described as a successful publication.[2]

## Restart, destroy or roll back

- **Restart:** “@fabian Restart [sandbox name].” Discards sandbox changes and returns it to the current live version, while keeping a sandbox available.[2]
- **Destroy:** “@fabian Destroy [sandbox name].” Removes the sandbox and its changes; the live site is not changed.[2]
- **Confirmation:** Both actions require Fabian to describe what will be lost and obtain a “yes” in #website. Anyone in that channel may confirm. Either action also cancels an active vote.[2]
- **Roll back a published update:** Contact German. Only German can request a rollback through his DM with Fabian, and he must confirm the particular update before it is undone.[2]

# 4. Progress, problems and useful links

## What to expect from Fabian

Fabian should acknowledge before starting, mention the requester, use top-level messages, and keep an editable status message current. During long waits, there should be an update at least once a minute. A separate final message confirms the actual result.[1][2]

- **👀** Request seen / work started.[1][2]
- **⏳** Work or publication in progress.[1][2]
- **✅** The relevant task is complete; for publication, the live result has been checked.[1][2]
- **⚠️** A problem or a question needing an answer; while awaiting a preview confirmation, 👀 may also remain.[1]

Reactions and progress messages never substitute for an article confirmation or a website vote; website votes are messages to @fabian.[1][2]

## If something goes wrong

- **No acknowledgment:** Mention @fabian in the correct channel and ask German to check access if there is still no response. A Slack API connection working does not by itself mean every team member’s messages are authorized. Do not share tokens or passwords in the channel. This is an operational troubleshooting recommendation.
- **Preview is wrong:** Request corrections before confirming. For news, approve the revised preview—not an earlier version.[1]
- **Changes are not visible:** Wait for the completion message, then refresh. News builds usually take 1–2 minutes and sandbox builds about 2–3 minutes, but these are estimates; news caching can last up to ten minutes. If a build is still missing after ten minutes, ask Fabian to check its status.[1][2]
- **Conflicting edits, failed builds or permission problems:** Fabian should explain the blocker and involve German where required rather than silently continuing.[1][2]

## Useful links

- Live website: https://forabrighterevanston.org/
- English news: https://forabrighterevanston.org/home/in-the-news/
- Spanish news: https://forabrighterevanston.org/es/noticias/

## Administrator readiness checklist

Before relying on the workflow for the whole team, verify that the intended requesters are authorized, Fabian receives messages in both channels, and the sandbox builds and voting checks operate as documented. GitHub Pages must use **GitHub Actions** as its build/deployment source for the sandbox workflow; merging the files alone does not establish that setup is complete.[2]

This guide does not change Slack access, deployment settings or the website. Changes to Fabian’s user-facing functionality require a review of this guide and a regenerated PDF in the same update.

## Sources

[1] https://github.com/germanespinosa/for-a-brighter-evanston/blob/main/docs/agents/fabian-news.md
[2] https://github.com/germanespinosa/for-a-brighter-evanston/blob/main/docs/agents/fabian-website.md
