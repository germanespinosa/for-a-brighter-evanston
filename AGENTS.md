# Team help document maintenance

When someone sends `-help` to Fabian as a regular message (trim surrounding whitespace), send the latest `docs/help/team-help.pdf` as a file attachment, with a short introduction. If attaching is unavailable, link to https://github.com/germanespinosa/for-a-brighter-evanston/raw/refs/heads/main/docs/help/team-help.pdf . This replaces the requested trigger `/help`; do not override Hermes' built-in slash command.

For every change to Fabian's user-facing functionality, update `docs/help/team-help.md` to reflect the actual behavior and regenerate `docs/help/team-help.pdf` in the same change. Review all relevant news/website manuals, commands, permissions, confirmation/voting rules and limitations; do not claim an unverified feature is operational.

Build after review: `python3 scripts/build_help_pdf.py` (requires ReportLab 4.x and DejaVu fonts).
Check before committing: `python3 scripts/build_help_pdf.py --check`.
Test the builder: `python3 -m unittest discover -s scripts/tests -v` (requires ReportLab and pypdf).
Commit the Markdown, PDF and `docs/help/reviewed-sources.json` together. The freshness workflow detects changed manuals, workflow files and helper scripts. It does not understand behavior or automatically rewrite prose: never regenerate only to silence a failure without reviewing the content. Functionality changes outside those tracked files require the same manual review.

Never commit credentials, internal chat transcripts or private user data to this public repository. Follow the operating manuals for authorization before posting or publishing changes; the help guide does not grant additional permissions.
