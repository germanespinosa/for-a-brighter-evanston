# For A Brighter Evanston

Website for the For A Brighter Evanston campaign on District 65 school closures, rebuilt from the Google Sites version of forabrighterevanston.org as a static site that GitHub Pages builds with Jekyll.

- Live (GitHub Pages): https://forabrighterevanston.org/
- Old Google Sites addresses are kept, so existing links keep working once the domain points here.

## Pages

| English | Spanish | Template |
|---|---|---|
| `/` | `/es/` | `_includes/pages/home.html` |
| `/home/in-the-news/` | `/es/noticias/` | `_includes/pages/news.html` |
| `/home/new-homes/` | `/es/nuevas-viviendas/` | `_includes/pages/new-homes.html` |
| `/home/write-to-the-board-issue/` | `/es/escriba-a-la-junta-issue/` | `_includes/pages/write.html` |

Each language's `index.html` is only front matter (title, description, language, link to the other language) plus one `include`. Both languages share the same template, so a layout change is made once.

## Common edits

| To change… | Edit |
|---|---|
| **News articles** | `data/news.json` — add an object to `articles` (see its `_readme`). The page loads this file in the browser and sorts by date. |
| Next meeting date (yellow bar, "Next up" card, calendar links, `.ics`) | `_data/event.yml` |
| Home page text, header/footer/menu labels, "Get updates" form | `_data/i18n/en.yml` and `_data/i18n/es.yml` |
| In the news page labels | `_data/news_page.yml` |
| New homes text and developments table | `_data/new_homes.yml` |
| Letter builder text (issues, sentences, board emails) | `assets/js/letter-content.js` |
| Hero slideshow photos | add files to `assets/img/hero/` and list them in `_data/hero.yml` |
| Sign-the-letter link, Instagram, email, Google Form links, signature counter | `_config.yml` → `links` |
| Colors, fonts, spacing | variables at the top of `assets/css/main.css` |

### Adding a news article

```json
{
  "date": "2026-11-05",
  "source": "Evanston RoundTable",
  "site": "RoundTable",
  "url": "https://evanstonroundtable.com/…",
  "title": "Headline in English",
  "summary": "One or two sentences.",
  "title_es": "Titular en español (optional)",
  "summary_es": "Resumen (optional)"
}
```

`date`, `source`, `url` and `title` are required. `python3 scripts/news_tool.py add entry.json` adds an entry safely (cleans the URL, refuses duplicates, validates the file); `python3 scripts/news_tool.py check` validates the file. The step-by-step procedure for the Fabian agent (adding and removing articles from #news requests) is in `docs/agents/fabian-news.md`. The Spanish page falls back to English when a Spanish field is missing. Keep the file valid JSON (commas between items, none after the last).

## Code layout

```
_config.yml            site settings and shared links
_layouts/default.html  <head>, header, alert bar, footer, dialogs, scripts
_includes/             header, footer, alert bar, updates dialog, calendar menu, icons, page templates
_data/                 text and data (see "Common edits")
assets/css/main.css    shared styles (tokens, header, buttons, forms, dialogs)
assets/css/<page>.css  page styles
assets/js/main.js      dialogs, Google Form thank-you, calendar menu
assets/js/home.js      slideshow, live signature count, share dialog
assets/js/news.js      renders data/news.json
assets/js/letter.js    letter builder (content in letter-content.js)
data/news.json         articles for In the news
```

No build tools or frameworks: plain HTML, CSS and JavaScript, with Jekyll includes so the header, footer and both languages stay in sync.

## Preview locally

```
bundle install
bundle exec jekyll serve --baseurl ""
```

Then open http://localhost:4000.

## Moving forabrighterevanston.org here

1. In the repository: **Settings → Pages → Custom domain** → `www.forabrighterevanston.org` (GitHub adds a `CNAME` file), then tick **Enforce HTTPS** once it is offered.
2. At the domain's DNS: `www` → CNAME `germanespinosa.github.io`; apex `forabrighterevanston.org` → A records `185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153`.
3. In `_config.yml` set `url: https://www.forabrighterevanston.org` and `baseurl: ""`.
