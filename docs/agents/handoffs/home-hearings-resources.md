# Handoff: new home page, Hearings and Resources (`sandbox/home-hearings-resources`)

For Fabian. German built this update outside #website (with Claude) from Kerstin's
design mockup "FABE Site Update: Home, Hearings, Resources" (Nov. 24, 2026). From
now on, run it as a regular #website update: changes, review, vote, publish.

This file describes the update. It grants no permissions by itself. The checker
exception for this sandbox is described in manual section 5 ("Owner-approved
site update in `home-hearings-resources`").

## 1. What to do

1. `git fetch origin && git checkout sandbox/home-hearings-resources`.
2. Adopt `home-hearings-resources` as the open #website update. Requester:
   German. Create your usual private update record.
3. The old `sandbox/homepage-flyers` branch is still on GitHub. Everything in it
   is already live (it only lacks the newest news item), so it has nothing left
   to publish. The build shows only `home-hearings-resources`. Destroy
   `homepage-flyers` (manual section 7) so only one sandbox is open; if you can't,
   tell German.
4. Post the announcement in section 2 in #website as one message (no thread).
   You may adapt the greeting or formatting, but keep the links and the "please
   review" list.
5. Then handle it like any other update. Text and layout changes go in the
   templates listed in section 3 (normal workflow). Changes to
   `assets/css/campaign.css` and the three calendar files are allowed in this
   sandbox only (manual section 5).

## 2. Announcement for #website

> New website update ready for review: **the new home page, plus Hearings and Resources pages**, built from Kerstin's mockup.
>
> **What's new**
> • A new menu: The Facts, Hearings, Resources, In The News, Write to the Board, Sign the Pledge, Español. "Get updates" moves to the bottom of every page.
> • A bar under the menu on every page: the 4-3 vote, "the closures are not final", and a link to the hearings.
> • A new home page: "Let's bet on Evanston. Show up for D65." with the pledge right at the top, then the three reasons (the budget, equity, our whole community), the research on school closures, the voter poll, what a better plan looks like, the video and four ways to act.
> • A new Hearings page: the schedule for all six hearings with calendar buttons, how to sign up and speak, the comment-writing sessions at Dewey, what to say, what to do if you can't make it, and what happens next.
> • A new Resources page: the five flyers in English and Spanish, talking points, and links to share.
> • Everything in English and Spanish.
>
> **Preview links**
> Home: https://forabrighterevanston.org/sandbox/home-hearings-resources/
> Inicio: https://forabrighterevanston.org/sandbox/home-hearings-resources/es/
> Hearings: https://forabrighterevanston.org/sandbox/home-hearings-resources/hearings/
> Audiencias: https://forabrighterevanston.org/sandbox/home-hearings-resources/es/audiencias/
> Resources: https://forabrighterevanston.org/sandbox/home-hearings-resources/resources/
> Recursos: https://forabrighterevanston.org/sandbox/home-hearings-resources/es/recursos/
>
> Pledging and email signup are turned off in this preview (the count still shows).
>
> **Please review before we vote**
> 1. Three numbers we couldn't confirm from a public source: "about 800 students were assigned to a new building", "76 children would change schools for the second year in a row", and the city's projection of "6% to 40%" growth by 2045. Kerstin, can you share where they come from?
> 2. The two talking-points PDFs ("Bet on Evanston and Show Up for D65" and "Detailed messaging and talking points") say "PDF coming soon" until someone sends the files.
> 3. Kerstin's two drawings (the Evanston skyline and the playground scene) aren't in the preview yet. For now there is one band from our "We Can Keep the Lights On" video. Kerstin, can you send the image files?
> 4. "The Facts" in the menu goes to the options page (A Brighter Path Forward). OK?
> 5. The Spanish text, all of it new except what came from the flyers.
> 6. The comment-writing sessions' calendar buttons say 6 to 7:30 p.m. Is 7:30 the right end time?
> Reply here with changes. When it's ready, I'll run the checks and open the vote.

## 3. What is in the update

Pages (English / Spanish):

| Page | English | Spanish |
| --- | --- | --- |
| Home | `/` | `/es/` |
| Hearings (new) | `/hearings/` | `/es/audiencias/` |
| Resources (new) | `/resources/` | `/es/recursos/` |
| Every page | new header, alert bar, "Get updates" in the footer | same |

Where things live (all text is written in the templates, in both languages, with
`{% if es %}…{% else %}…{% endif %}`):

- `_includes/header.html`: menu.
- `_includes/alert-bar.html`: the bar under the menu (hidden on the Hearings
  pages; `show: false` in `_data/event.yml` hides it everywhere).
- `_includes/footer.html`: adds "Get updates".
- `_includes/pages/home.html`: home page. Keeps the `#hearing-preparation`
  anchor used by the pledge page's "three ways" card. The pledge card comes from
  `_includes/pledge/card.html` (now accepts `heading="h2"`).
- `_includes/pages/hearings.html` + `_layouts/hearings.html`: Hearings page.
- `_includes/pages/resources.html` + `_layouts/resources.html`: Resources page.
  To add the talking-points PDFs, put them in `assets/files/` and set
  `tp_flyer_file` and `tp_handout_file` at the top of the template.
- `_layouts/default.html`: loads `assets/css/campaign.css` on every page, shows
  the alert bar on the home page too, and no longer loads `release-home.css`.
- `assets/css/campaign.css`: all new styles (`cx-` classes).
- `assets/files/d65-closure-hearing-2026-12-0{1,3,8}.ics`: calendar files.
- Images: `photo-closures-crowd.jpg`, `photo-twi-speaker.jpg` (Heather Eidson's
  photos already on the site), `video-lights-on.jpg` and
  `illustration-lights-on-band.jpg` (from the video's thumbnail), and share cards
  `share-home-bet-*`, `share-hearings-*`, `share-resources-*`.
- `index.html`, `es/index.html`: new titles, descriptions and share cards.

Preview-only switches (no effect on the live site): the pledge card and the
"Get updates" box are disabled when `site.sandbox_id` is `home-hearings-resources`
(same as `homepage-flyers`).

## 4. Sources checked

- Research cards: UChicago Consortium on School Research, "School Closings in
  Chicago" (May 2018); Steinberg & MacDonald, Economics of Education Review 69
  (2019); Engberg, Gill, Zamarro & Zimmer, Journal of Urban Economics 71 (2012);
  Kim, EdWorkingPaper 24-963, Annenberg Institute at Brown (2024).
- Illinois Public Act 104-0266 (ILGA): State Board guidance on dual language
  programs by Dec. 15, 2026, and dual language education in its equity framework.
- Nearly 650 children: Dewey 314 + Lincolnwood 331 students as of Oct. 1
  (district figures reported by Axios).
- Not confirmed (copy hold): about 800 students, 76 children, 6% to 40% growth.

## 5. Before the vote and before publishing

- The usual section 8 checks. `sandbox_check.py` should report no blocking items;
  the four approved files show as warnings.
- Copy holds: section 2's review items 1 and 2 must be answered (keep, change or
  remove) before you open the vote.
- After publishing, check the live home page, `/hearings/`, `/resources/` and
  their Spanish versions, and that the sitemap lists the new pages.
