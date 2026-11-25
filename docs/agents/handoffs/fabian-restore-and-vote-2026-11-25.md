# Fabian: restore full capability and get the home/hearings/resources update ready for a vote

**From:** German (written with Claude), Nov. 25, 2026
**Based on:** your status report of Nov. 24, 2026, 9:56 p.m. Central, and the repository as of `main` `342d3be`, sandbox `de7508a`, PR #13 (open, mergeable)

This is a work list. It gives you **no permission** beyond your manuals
(`docs/agents/fabian-website.md`, `fabian-news.md`) and German's explicit messages.
Where a step says "ask German", wait for his answer in Slack before acting.
Work in the order below. Report back with the checklist in section D.

---

## A. Unblock the vote (do first)

### A1. Merge PR #13 (after German says so)
PR #13 adds the scoped checker exception for `assets/css/campaign.css` and the
three hearing `.ics` files in `sandbox/home-hearings-resources`, the manual and
help-guide updates, the handoff, and this file.

1. Ask German in a DM: "OK to merge PR #13 (checker exception for the
   home-hearings-resources update)?" Merge only after a clear yes from German.
2. After merging, in a **fresh worktree** (see B2), from `main`:
   - `python3 -m unittest scripts.tests.test_site_update_files -v` → 6 tests pass.
   - `python3 scripts/build_help_pdf.py --check` → current.
   - Check that the Pages deploy for the merge commit succeeds.
3. Check out `sandbox/home-hearings-resources`, merge `origin/main` into it
   (normal "bring the sandbox up to date" step), push, and run
   `python3 scripts/sandbox_check.py --base origin/main`.
   Expected: **BLOCKING (0)**, "OK TO VOTE (review warnings)"; the four approved
   files appear only as warnings. If anything still blocks, stop and report the
   exact message to German; do not work around the checker.

### A2. Clear the content holds (team decisions)
Post in #website (one message, @-mention Kerstin), and record each answer in your
update record. Every text change must be made in **both** English and Spanish
(same template, the `{% if es %}` branch).

| # | Hold | Where | What to do with the answer |
|---|------|-------|----------------------------|
| 1 | "about 800 students were assigned to a new building" | `_includes/pages/home.html`, section `#last-closures` | Keep only with a source Kerstin names; otherwise reword or remove. |
| 2 | "76 children would change schools for the second year in a row" | same section, `cx-big-line` | Same. If removed, keep the sentence that follows readable. |
| 3 | City projection "6% to 40% by 2045" | `home.html`, card "A growing city" | Same. |
| 4 | Talking-points PDFs ("Bet on Evanston and Show Up for D65", "Detailed messaging and talking points") | `_includes/pages/resources.html` | If supplied: check they are PDFs ≤ 5 MB without scripts, add to `assets/files/`, set `tp_flyer_file` / `tp_handout_file` at the top of the template. If not supplied before the vote: ask the team whether to publish with "PDF coming soon" or remove the cards. |
| 5 | Kerstin's two drawings (night skyline, playground scene) | `home.html`: `.cx-illustration` band before `#community`; a second band before `#better-plan` | If supplied: resize to ≤ 2000 px wide, strip metadata, add under `assets/img/`, replace `illustration-lights-on-band.jpg` and add the second band. Otherwise keep the current band. |
| 6 | "The Facts" menu link → options page | `_includes/header.html` (`url_facts`) | Change only if the team picks another page. |
| 7 | Comment-writing sessions end time (preview says 6–7:30 p.m.) | `_includes/pages/hearings.html`: the two `ws_base` links (`dates=…T180000/…T193000`) | Set the confirmed end time in both links. |
| 8 | Spanish text | all three templates | Ask a Spanish-speaking reviewer to read the Spanish preview pages; apply corrections. |

Do not open the vote while 1–3 are unanswered. 4–8 may go to the vote if the team
explicitly accepts the current state in #website.

### A3. Fix small tap targets on phones
Your phone review flagged small tap targets on the home and hearings pages. In
this sandbox `assets/css/campaign.css` is allowed after A1. Likely candidates:
`.cx-nav__list a` and `.cx-nav__lang` (header), `.cx-alert a`,
`.cx-night__cal a` (calendar links), `.cx-card__link`, `.cx-link`,
`.cx-flyer__links a`, `.cx-footer-updates`.

1. Classify each finding: which element, which page, measured size.
2. Fix only real problems, aiming for at least 44 × 44 px of tappable area
   (padding or `min-height` + `display: inline-flex; align-items: center`), keeping
   every selector under a `.cx…` class.
3. Re-run the phone screenshots (390 px wide) for `/`, `/es/`, `/hearings/`,
   `/es/audiencias/`, `/resources/`, `/es/recursos/` and confirm no horizontal
   overflow. Use real viewport screenshots when full-page stitching looks wrong.

### A4. Final checks before the vote (manual section 8)
- `sandbox_check.py` with `--url https://forabrighterevanston.org/sandbox/home-hearings-resources/` (link check) → 0 blocking.
- Desktop and phone screenshots of all six pages; English and Spanish.
- Links to check by hand: calendar files download and open; Google Calendar
  links show the right date and time (Central); "Get directions"; D65 notice and
  guidelines; partner links; `#pledge` buttons scroll to the pledge card;
  `#hearing-preparation` still exists on the home page (the pledge page links to it).
- Sharing cards: `share-home-bet-*`, `share-hearings-*`, `share-resources-*`
  show in the preview review.
- Pledge card in the preview shows the count and says signing is disabled.

### A5. Open the vote (manual section 9)
When A1–A4 are done and the holds are resolved or explicitly accepted, open the
normal team vote in #website with: the six preview links, what changed (from the
handoff announcement), how each hold was resolved, and the checker result.
After approval, publish as usual, verify the live pages (section 5 of
`home-hearings-resources.md`), and destroy the sandbox. `homepage-flyers` is
already gone; nothing to do there.

---

## B. Restore full capability

### B1. Disk space (host root filesystem 96% full, ~4.7 GB free)
Goal: at least 20% free. **Delete nothing without German's approval.**
1. Read-only inventory with sizes and owners (`du -xh --max-depth=2`) of
   `~/.hermes`, `~/.cache`, `~/fabian-workspaces`, `~/.fabian/website-drafts`,
   logs and Docker/package caches if present.
2. Sort candidates into: (a) regenerable caches (pip, npm, Playwright, Jekyll,
   `~/.cache/*`), (b) worktrees/drafts of sandboxes already published or destroyed
   (`homepage-flyers`, older closed updates), (c) old logs that can be rotated or
   compressed, (d) anything belonging to other Hermes profiles or backups → **do not
   touch**, list only.
3. DM German the table (path, size, category, what is lost if deleted) and ask
   which rows to remove. Act only on the rows he approves; re-run `df -h` and
   report.
4. Propose log rotation for the gateway log if it is large; do not change
   configuration without approval.

### B2. Primary checkout 219 commits behind, with local changes
1. Do not reset, clean, stash or pull in
   `/home/german/fabian-workspaces/for-a-brighter-evanston`.
2. Create a fresh worktree from `origin/main` for all new work
   (`git worktree add …`).
3. List the old checkout's modified and untracked files (`git status`, `git diff --stat`)
   and report them to German with your best guess of what each is. Ask whether to
   keep, move to a branch, or discard. Only then reconcile.

### B3. Slack responsiveness
1. Until changed, #website needs an `@fabian` mention. Say so once in #website.
2. Ask German whether to add #website as a free-response channel. If he approves:
   make the configuration change, restart the gateway as the manual allows, and
   live-test one unmentioned and one mentioned message in #website. Report the result.
3. Watch `logs/gateway.log` for Socket Mode disconnects. If they repeat, report times
   and any messages that appear to be missing.

### B4. Daily news
After the Nov. 25, 10:00 a.m. Central run, confirm the job status is `ok` and the
numbered message is in #news. If it fails, report the error; don't rerun it
manually without the usual approval.

### B5. Live pledge risks (paused, needs German's decision)
German paused the pledge fixes. **Do not change the pledge, the Apps Script or
the Sheet.** Ask German whether to resume, and with what scope. The known items:
1. Submissions classified as too fast (< 2.5 s) or spam get a success-shaped
   response without being counted. Real people with browser autofill could be
   affected.
2. The embed form has no `method="post"`; without JavaScript the browser can put
   name and email in the URL.
3. The email field is not stripped of formula prefixes before the Sheet write
   (name fields are).
4. A thank-you is not proof of Mailchimp subscription; no readback exists.
If German says to resume, do it as its own sandbox with tests, separate from this
update.

---

## C. Do not
- Publish, merge or delete anything without the approvals named above.
- Edit the pledge backend, Sheet, Mailchimp settings or other restricted files
  outside the scoped exception.
- Delete other Hermes profiles' data, backups or drafts.
- Treat HTTP 200 as proof that a feature works.

## D. Report back to German (checklist)
- [ ] PR #13 merged (with German's OK); tests and deploy green
- [ ] Sandbox updated from main; checker BLOCKING (0)
- [ ] Holds 1–8: answer and change for each
- [ ] Tap targets: findings and fixes; phone screenshots OK
- [ ] Final checks done; vote opened (link) → result → published and verified
- [ ] Disk: inventory sent; approved cleanup done; new `df -h`
- [ ] Old checkout: file list sent; decision; fresh worktree in use
- [ ] Slack: decision on #website free-response; test result
- [ ] News run Nov. 25: status
- [ ] Pledge: German's decision recorded (resume / stay paused)
