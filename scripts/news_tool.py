#!/usr/bin/env python3
"""Check and update data/news.json for the In the news page.

Usage (from the repository root):
  python3 scripts/news_tool.py check
      Validate the whole file. Exit code 0 = OK, 1 = problems (listed).

  python3 scripts/news_tool.py find <url>
      Say whether an article with this URL (after cleanup) is already listed.

  python3 scripts/news_tool.py add <entry.json>
      Add one article from a JSON file holding a single object, e.g.
        {"date": "2026-11-05", "source": "Evanston RoundTable",
         "site": "Evanston RoundTable", "url": "https://...",
         "title": "...", "summary": "...",
         "title_es": "...", "summary_es": "..."}
      The URL is cleaned (tracking parameters removed), duplicates are
      refused, the entry is placed at the top of the list, and the file is
      validated before it is saved. Nothing is written if anything fails.

  python3 scripts/news_tool.py search [words...] [--source TEXT]
                                     [--date YYYY-MM-DD] [--from YYYY-MM-DD]
                                     [--to YYYY-MM-DD] [--month YYYY-MM]
      List articles matching ALL the given filters. Words are matched,
      case-insensitively, against the title, Spanish title, summary, Spanish
      summary, source and URL. Each match is printed in full (date, source,
      title, summary, URL) so it can be shown to the user for confirmation.

  python3 scripts/news_tool.py remove <url>
      Remove the one article whose URL matches (after cleanup), validate the
      file and save it. Prints the removed entry. Nothing is written if the
      URL doesn't match exactly one article.

Only the Python standard library is used.
"""
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

NEWS = Path(__file__).resolve().parent.parent / "data" / "news.json"

REQUIRED = ["date", "source", "url", "title"]
ALLOWED = REQUIRED + ["site", "summary", "title_es", "summary_es",
                      "alt_url", "alt_label", "alt_label_es"]
ORDER = ["date", "source", "site", "url", "title", "summary",
         "title_es", "summary_es", "alt_url", "alt_label", "alt_label_es"]
TRACKING = re.compile(r"^(utm_.*|fbclid|gclid|mc_cid|mc_eid|cmpid|ref_src|smid|igshid)$", re.I)


def clean_url(url):
    """Drop tracking parameters and fragments; keep everything else."""
    parts = urlsplit(url.strip())
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not TRACKING.match(k)]
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, urlencode(query), ""))


def url_key(url):
    """Comparison key: cleaned URL, no scheme, no www, no trailing slash, lowercase."""
    parts = urlsplit(clean_url(url))
    host = parts.netloc.removeprefix("www.")
    path = parts.path.rstrip("/")
    q = ("?" + parts.query) if parts.query else ""
    return (host + path + q).lower()


def load():
    text = NEWS.read_text(encoding="utf-8")
    return json.loads(text)


def problems_in(data):
    errs = []
    if not isinstance(data, dict) or not isinstance(data.get("articles"), list):
        return ['Top level must be an object with an "articles" list.']
    seen = {}
    for i, a in enumerate(data["articles"]):
        where = f"articles[{i}]"
        if not isinstance(a, dict):
            errs.append(f"{where}: must be an object")
            continue
        label = f'{where} ("{str(a.get("title", ""))[:50]}")'
        for k in REQUIRED:
            if not str(a.get(k, "")).strip():
                errs.append(f"{label}: missing {k}")
        for k in a:
            if k not in ALLOWED:
                errs.append(f"{label}: unknown field {k!r}")
            elif not isinstance(a[k], str):
                errs.append(f"{label}: {k} must be text")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(a.get("date", ""))):
            errs.append(f"{label}: date must look like 2026-11-05")
        for k in ("url", "alt_url"):
            if k in a and not str(a[k]).startswith(("https://", "http://")):
                errs.append(f"{label}: {k} must start with https://")
        if "alt_url" in a and not a.get("alt_label"):
            errs.append(f"{label}: alt_url needs alt_label")
        if a.get("url"):
            key = url_key(a["url"])
            if key in seen:
                errs.append(f"{label}: duplicate of articles[{seen[key]}]")
            seen.setdefault(key, i)
    return errs


def save(data):
    NEWS.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def cmd_check():
    try:
        data = load()
    except json.JSONDecodeError as e:
        print(f"INVALID JSON: {e}")
        return 1
    errs = problems_in(data)
    if errs:
        print("PROBLEMS:\n- " + "\n- ".join(errs))
        return 1
    print(f"OK: {len(data['articles'])} articles")
    return 0


def cmd_find(url):
    data = load()
    key = url_key(url)
    for i, a in enumerate(data["articles"]):
        if url_key(a.get("url", "")) == key or url_key(a.get("alt_url", "") or "x://") == key:
            print(f"FOUND at articles[{i}]: {a['date']} | {a['source']} | {a['title']}")
            return 0
    print("NOT FOUND")
    return 1


def cmd_add(path):
    entry = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(entry, dict):
        print("The entry file must hold one JSON object.")
        return 1
    entry = {k: v.strip() if isinstance(v, str) else v for k, v in entry.items() if v not in ("", None)}
    if "url" in entry:
        entry["url"] = clean_url(entry["url"])
    if "alt_url" in entry:
        entry["alt_url"] = clean_url(entry["alt_url"])
    entry.setdefault("site", entry.get("source", ""))
    entry = {k: entry[k] for k in ORDER if k in entry} | {k: v for k, v in entry.items() if k not in ORDER}

    data = load()
    key = url_key(entry.get("url", ""))
    for i, a in enumerate(data["articles"]):
        if url_key(a.get("url", "")) == key:
            print(f"DUPLICATE: already listed at articles[{i}]: {a['title']}")
            return 1
    data["articles"].insert(0, entry)
    errs = problems_in(data)
    if errs:
        print("NOT SAVED. PROBLEMS:\n- " + "\n- ".join(errs))
        return 1
    save(data)
    print(f"ADDED: {entry['date']} | {entry['source']} | {entry['title']}")
    print(f"OK: {len(data['articles'])} articles")
    return 0


def show(i, a):
    print(f"[{i}] {a.get('date')} | {a.get('source')}")
    print(f"    Title:   {a.get('title')}")
    print(f"    Summary: {a.get('summary', '(no summary)')}")
    if a.get("title_es"):
        print(f"    Título:  {a.get('title_es')}")
    print(f"    URL:     {a.get('url')}")


def cmd_search(args):
    opts, words, it = {}, [], iter(args)
    for x in it:
        if x in ("--source", "--date", "--from", "--to", "--month"):
            opts[x[2:]] = next(it, "")
        else:
            words.append(x.lower())
    data = load()
    hits = []
    for i, a in enumerate(data["articles"]):
        hay = " ".join(str(a.get(k, "")) for k in ("title", "title_es", "summary", "summary_es", "source", "site", "url")).lower()
        d = a.get("date", "")
        if any(w not in hay for w in words):
            continue
        if "source" in opts and opts["source"].lower() not in (a.get("source", "") + " " + a.get("site", "")).lower():
            continue
        if "date" in opts and d != opts["date"]:
            continue
        if "from" in opts and d < opts["from"]:
            continue
        if "to" in opts and d > opts["to"]:
            continue
        if "month" in opts and not d.startswith(opts["month"]):
            continue
        hits.append((i, a))
    for i, a in hits:
        show(i, a)
    print(f"MATCHES: {len(hits)}")
    return 0 if hits else 1


def cmd_remove(url):
    data = load()
    key = url_key(url)
    idx = [i for i, a in enumerate(data["articles"]) if url_key(a.get("url", "")) == key]
    if len(idx) != 1:
        print(f"NOT REMOVED: {len(idx)} articles have this URL (need exactly 1)")
        return 1
    removed = data["articles"].pop(idx[0])
    errs = problems_in(data)
    if errs:
        print("NOT REMOVED. PROBLEMS:\n- " + "\n- ".join(errs))
        return 1
    save(data)
    print("REMOVED:")
    show(idx[0], removed)
    print(f"OK: {len(data['articles'])} articles")
    return 0


if __name__ == "__main__":
    if sys.argv[1:2] == ["search"]:
        sys.exit(cmd_search(sys.argv[2:]))
    if sys.argv[1:2] == ["remove"] and len(sys.argv) == 3:
        sys.exit(cmd_remove(sys.argv[2]))
    args = sys.argv[1:]
    if args[:1] == ["check"] and len(args) == 1:
        sys.exit(cmd_check())
    if args[:1] == ["find"] and len(args) == 2:
        sys.exit(cmd_find(args[1]))
    if args[:1] == ["add"] and len(args) == 2:
        sys.exit(cmd_add(args[1]))
    print(__doc__)
    sys.exit(2)
