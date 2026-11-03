#!/usr/bin/env python3
"""Validate the open sandbox update before a publish vote.

Run from the repository root, on the sandbox branch:

  python3 scripts/sandbox_check.py [--base origin/main] [--url https://forabrighterevanston.org/sandbox/<id>/]

It compares the sandbox branch with the live site (main) and reports:

  BLOCKING   problems that must be fixed before a vote can start
             (changes outside what #website may change, unsafe HTML,
             broken page settings, news changes, broken pages or links)
  WARNINGS   things that will probably look or work wrong
  SPANISH    which changed content has, or lacks, a Spanish counterpart
  CHANGES    a plain list of what changed, for the summary to the group

With --url it also opens every changed page on the deployed sandbox and
checks that it loads and that its links and images work.

Exit code: 0 = no blocking problems, 1 = blocking problems, 2 = usage error.
Uses only the Python standard library (PyYAML is used for YAML if present).
"""
import argparse
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------- policy ---
# What #website users may change. Everything else is structural.
TEXT_DATA_FILES = {
    "_data/i18n/en.yml", "_data/i18n/es.yml",       # home page, header/footer labels
    "_data/new_homes.yml", "_data/news_page.yml",   # page text and tables
    "_data/event.yml", "_data/hero.yml",            # next meeting, hero photo list
}
MEDIA_DIRS = ("assets/img/", "assets/files/")
MEDIA_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".pdf"}
PAGE_EXT = {".html", ".md"}
STRUCTURAL_PREFIXES = (
    "_layouts/", "_includes/", "_plugins/", "_sass/", "assets/css/", "assets/js/",
    ".github/", "scripts/", "docs/", "data/", "sandbox/",
)
STRUCTURAL_FILES = {
    "_config.yml", "CNAME", "Gemfile", "Gemfile.lock", "robots.txt", "sitemap.xml",
    "favicon.svg", "404.html", "d65-board-meeting.ics", "README.md", ".gitignore",
}
MEDIA_WARN_BYTES = 500 * 1024
MEDIA_MAX_BYTES = 5 * 1024 * 1024

UNSAFE = [
    (re.compile(r"<\s*script\b", re.I), "a <script> tag"),
    (re.compile(r"<\s*style\b", re.I), "a <style> block"),
    (re.compile(r"<\s*(iframe|object|embed|frame|frameset|applet)\b", re.I), "an embedded frame or object"),
    (re.compile(r"<\s*form\b", re.I), "a <form>"),
    (re.compile(r"<\s*link\b", re.I), "a <link> tag"),
    (re.compile(r"<\s*meta\b", re.I), "a <meta> tag"),
    (re.compile(r"<\s*base\b", re.I), "a <base> tag"),
    (re.compile(r"\son[a-z]+\s*=", re.I), "an inline event handler (onclick=…)"),
    (re.compile(r"javascript\s*:", re.I), "a javascript: link"),
    (re.compile(r"{%-?\s*(include|include_relative|capture|assign\s+site|raw)\b", re.I), "Liquid template code other than links"),
]
WARN_PATTERNS = [
    (re.compile(r"\sstyle\s*=", re.I), "inline style=\"…\" (use the site's existing styles instead)"),
    (re.compile(r"""\s(?:href|src)\s*=\s*["']/(?!/)""", re.I),
     "a link or image starting with \"/\" without | relative_url (it breaks in the sandbox; write {{ '/path/' | relative_url }})"),
    (re.compile(r"""\s(?:href|src)\s*=\s*["']https?://(www\.)?forabrighterevanston\.org""", re.I),
     "a full link to forabrighterevanston.org (use {{ '/path/' | relative_url }} so it works in the sandbox too)"),
    (re.compile(r"""<img\b[^>]*\ssrc\s*=\s*["']https?://""", re.I), "an image loaded from another website (upload it to assets/img/ instead)"),
    (re.compile(r"<img\b(?![^>]*\salt\s*=)[^>]*>", re.I), "an image without alt text"),
]


def git(*args):
    return subprocess.run(["git", "-C", str(ROOT), *args], check=True, capture_output=True, text=True).stdout


def git_show(rev, path):
    try:
        return git("show", f"{rev}:{path}")
    except subprocess.CalledProcessError:
        return None


def load_yaml(text):
    try:
        import yaml  # type: ignore
        return yaml.safe_load(text)
    except ImportError:
        return None


def split_front_matter(text):
    if not text.startswith("---"):
        return None, text
    end = text.find("\n---", 3)
    if end < 0:
        return None, text
    return text[3:end].strip("\n"), text[end + 4:]


def parse_front_matter(fm):
    data = load_yaml(fm) if fm is not None else None
    if data is None and fm is not None:  # tiny fallback parser: key: value lines
        data = {}
        for line in fm.splitlines():
            m = re.match(r"^([A-Za-z_]+):\s*(.*)$", line)
            if m:
                data[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return data if isinstance(data, dict) else {}


def key_paths(obj, prefix=""):
    """Dict keys only (list items are content and may change length)."""
    out = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{prefix}.{k}" if prefix else str(k)
            out.add(p)
            out |= key_paths(v, p)
    elif isinstance(obj, list):
        for v in obj:
            out |= key_paths(v, prefix + "[]")
    return out


def flat_values(obj, prefix=""):
    out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(flat_values(v, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.update(flat_values(v, f"{prefix}[{i}]"))
    else:
        out[prefix] = obj
    return out


def page_url(path, fm):
    if fm.get("permalink"):
        return str(fm["permalink"])
    p = path[:-len(Path(path).suffix)]
    if p.endswith("index"):
        p = p[:-5]
    else:
        p += "/"
    return "/" + p.lstrip("/")


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        for attr in ("href", "src"):
            if a.get(attr) and tag in ("a", "img", "link", "script", "source"):
                self.links.append((tag, a[attr]))


def fetch(url, method="GET"):
    req = urllib.request.Request(url, method=method, headers={"User-Agent": "fabian-sandbox-check"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, (r.read().decode("utf-8", "replace") if method == "GET" else "")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:  # network errors
        return 0, str(e)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="origin/main", help="what the sandbox is compared to (default origin/main)")
    ap.add_argument("--url", help="deployed sandbox address, e.g. https://forabrighterevanston.org/sandbox/faq-page/")
    ap.add_argument("--json", action="store_true", help="print the report as JSON")
    args = ap.parse_args()

    blocking, warnings, spanish, changes, notes = [], [], [], [], []

    try:
        diff = git("diff", "--name-status", "-M", f"{args.base}...HEAD")
    except subprocess.CalledProcessError as e:
        print(f"Could not compare with {args.base}: {e.stderr.strip()}")
        return 2

    entries = []
    for line in diff.splitlines():
        parts = line.split("\t")
        status = parts[0][0]
        if status == "R":
            entries.append(("D", parts[1]))
            entries.append(("A", parts[2]))
        else:
            entries.append((status, parts[-1]))

    if not entries:
        notes.append("No changes compared with the live site.")

    changed_pages = []   # (path, front matter, body)
    changed_data = []

    for status, path in entries:
        ext = Path(path).suffix.lower()
        verb = {"A": "added", "M": "changed", "D": "deleted"}.get(status, "changed")

        if path == "data/news.json":
            blocking.append("The news list (data/news.json) was changed. News is managed only in #news; this change must be removed.")
            continue
        if path in STRUCTURAL_FILES or path.startswith(STRUCTURAL_PREFIXES) or path.startswith("."):
            blocking.append(f"{path} was {verb}. It's part of the site's structure, which #website updates can't change.")
            continue

        if path in TEXT_DATA_FILES:
            if status == "D":
                blocking.append(f"{path} was deleted. Page text files can be edited but not deleted.")
                continue
            changed_data.append(path)
            changes.append(f"Text {verb}: {path}")
            continue

        if path.startswith(MEDIA_DIRS):
            if ext not in MEDIA_EXT:
                blocking.append(f"{path}: {ext or 'this'} files aren't allowed. Use JPG, PNG, WebP, GIF or PDF.")
                continue
            if status == "D":
                if git_show(args.base, path) is not None:
                    warnings.append(f"{path} was deleted from the live site's files; check nothing still uses it.")
                changes.append(f"File deleted: {path}")
                continue
            size = (ROOT / path).stat().st_size
            if size > MEDIA_MAX_BYTES:
                blocking.append(f"{path} is {size/1048576:.1f} MB; the limit is 5 MB. Resize or compress it.")
            elif size > MEDIA_WARN_BYTES and ext in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
                warnings.append(f"{path} is {size//1024} KB; images over 500 KB slow the site down on phones. Resize it to about 1600 px wide.")
            changes.append(f"File {verb}: {path} ({size//1024} KB)")
            continue

        if ext in PAGE_EXT and not path.startswith("_"):
            if status == "D":
                blocking.append(f"The page {path} was deleted. Deleting published pages breaks existing links; ask German.")
                continue
            text = (ROOT / path).read_text(encoding="utf-8")
            fm_text, body = split_front_matter(text)
            fm = parse_front_matter(fm_text)
            changed_pages.append((path, fm, body, status))
            changes.append(f"Page {verb}: {path} → {page_url(path, fm)}")
            continue

        blocking.append(f"{path} was {verb}. Only pages, page text files and files in assets/img/ or assets/files/ may be changed.")

    # ---- pages
    all_pages = set(git("ls-files").splitlines())
    for path, fm, body, status in changed_pages:
        label = f"{path}"
        if fm is None or not fm:
            blocking.append(f"{label}: missing the page settings block (front matter between --- lines).")
            continue
        if fm.get("layout") != "default":
            blocking.append(f"{label}: layout must be \"default\" (found {fm.get('layout')!r}).")
        if fm.get("lang") not in ("en", "es"):
            blocking.append(f"{label}: lang must be \"en\" or \"es\" (found {fm.get('lang')!r}).")
        for k in ("title", "description"):
            if not str(fm.get(k, "")).strip():
                blocking.append(f"{label}: missing {k}.")
        allowed_fm = {"layout", "lang", "title", "description", "alt_url", "share_image", "nav", "css", "scripts", "body_class", "permalink", "is_home"}
        extra = set(fm) - allowed_fm
        if extra:
            warnings.append(f"{label}: unusual settings {sorted(extra)}.")
        if status == "A":
            for k in ("css", "scripts", "nav", "is_home"):
                if k in fm:
                    blocking.append(f"{label}: new pages can't set {k!r}; that changes how the site works.")
        base_text = git_show(args.base, path)
        if base_text is not None:
            base_fm = parse_front_matter(split_front_matter(base_text)[0])
            for k in ("css", "scripts", "nav", "is_home", "permalink", "layout", "lang"):
                if base_fm.get(k) != fm.get(k):
                    blocking.append(f"{label}: the {k!r} setting was changed; that's structural.")

        # Only flag what this update introduced (existing pages may use includes by design)
        base_body = split_front_matter(base_text)[1] if base_text is not None else ""
        for rx, what in UNSAFE:
            if len(rx.findall(body)) > len(rx.findall(base_body)):
                blocking.append(f"{label}: adds {what}, which isn't allowed in page content.")
        for rx, what in WARN_PATTERNS:
            if len(rx.findall(body)) > len(rx.findall(base_body)):
                warnings.append(f"{label}: contains {what}.")
        if body.count("{%") != body.count("%}") or body.count("{{") != body.count("}}"):
            blocking.append(f"{label}: unbalanced Liquid braces ({{{{ }}}} or {{% %}}).")

        # Spanish counterpart
        alt = fm.get("alt_url")
        lang = fm.get("lang")
        if not alt:
            if lang == "en":
                spanish.append(f"{page_url(path, fm)} has no Spanish version (no alt_url).")
            else:
                spanish.append(f"{page_url(path, fm)} (Spanish) has no English version linked (no alt_url).")
        else:
            target = str(alt).strip("/")
            candidates = {f"{target}/index.html", f"{target}/index.md", f"{target}.html", f"{target}.md"} if target else {"index.html"}
            found = [c for c in candidates if c in all_pages or (ROOT / c).exists()]
            if not found:
                blocking.append(f"{label}: alt_url {alt} points to a page that doesn't exist.")
            else:
                other = found[0]
                other_changed = any(p == other for p, *_ in changed_pages)
                if status == "A" and not other_changed:
                    warnings.append(f"{label}: links to {alt} as its other-language version, but that page is not new or changed in this update.")
                if status == "M" and not other_changed:
                    spanish.append(f"{page_url(path, fm)} changed, but its {'Spanish' if lang == 'en' else 'English'} version ({alt}) did not.")
                else:
                    spanish.append(f"{page_url(path, fm)} ↔ {alt}: both versions are in this update.")

    # ---- text data files
    for path in changed_data:
        head_text = (ROOT / path).read_text(encoding="utf-8")
        base_text = git_show(args.base, path) or ""
        head, base = load_yaml(head_text), load_yaml(base_text)
        if head is None:
            try:
                import yaml  # noqa: F401
                blocking.append(f"{path}: not valid YAML after the change.")
            except ImportError:
                warnings.append(f"{path}: couldn't validate YAML here (PyYAML not installed); the sandbox build will show errors.")
            continue
        added = key_paths(head) - key_paths(base)
        removed = key_paths(base) - key_paths(head)
        if added or removed:
            blocking.append(f"{path}: settings were added or removed ({', '.join(sorted(added | removed)[:6])}); only the text values may change.")
        hv, bv = flat_values(head), flat_values(base)
        changed_keys = sorted(k for k in hv if bv.get(k) != hv[k])
        for k in changed_keys:
            v = hv[k]
            if isinstance(v, str) and any(rx.search(v) for rx, _ in UNSAFE):
                blocking.append(f"{path} → {k}: contains code that isn't allowed.")
        if changed_keys:
            changes.append(f"  {path}: {len(changed_keys)} value(s) changed: {', '.join(changed_keys[:8])}{' …' if len(changed_keys) > 8 else ''}")
        pair = {"_data/i18n/en.yml": "_data/i18n/es.yml", "_data/i18n/es.yml": "_data/i18n/en.yml"}.get(path)
        if pair:
            other_head = load_yaml((ROOT / pair).read_text(encoding="utf-8"))
            other_base = load_yaml(git_show(args.base, pair) or "")
            ov, ob = flat_values(other_head or {}), flat_values(other_base or {})
            other_changed = {k for k in ov if ob.get(k) != ov[k]}
            missing = [k for k in changed_keys if k not in other_changed]
            if missing:
                spanish.append(f"{path} changed {', '.join(missing[:6])}, but {pair} did not change the same text.")
            elif changed_keys:
                spanish.append(f"{path} and {pair}: the same text was changed in both languages.")
        elif path in ("_data/new_homes.yml", "_data/news_page.yml", "_data/event.yml"):
            en = [k for k in changed_keys if k.startswith("en.")]
            es = [k for k in changed_keys if k.startswith("es.")]
            missing = [k for k in en if "es." + k[3:] not in es] + [k for k in es if "en." + k[3:] not in en]
            if missing:
                spanish.append(f"{path}: changed in one language only: {', '.join(missing[:6])}.")
            elif en or es:
                spanish.append(f"{path}: changes made in both English and Spanish.")

    # ---- deployed sandbox checks
    if args.url:
        base_url = args.url if args.url.endswith("/") else args.url + "/"
        status, _ = fetch(base_url)
        if status != 200:
            blocking.append(f"The sandbox home page {base_url} doesn't load (HTTP {status}). Wait for the build, or check the build status.")
        checked = set()
        for path, fm, body, st in changed_pages:
            url = urljoin(base_url, page_url(path, fm).lstrip("/"))
            code, html = fetch(url)
            if code != 200:
                blocking.append(f"{url} doesn't load (HTTP {code}).")
                continue
            parser = LinkParser()
            parser.feed(html)
            for tag, link in parser.links:
                full = urljoin(url, link)
                parts = urlsplit(full)
                if parts.scheme not in ("http", "https") or full in checked:
                    continue
                checked.add(full)
                if parts.netloc != urlsplit(base_url).netloc:
                    continue  # outside links aren't checked
                c, _ = fetch(full.split("#")[0], method="HEAD")
                if c == 405:
                    c, _ = fetch(full.split("#")[0])
                if c >= 400 or c == 0:
                    blocking.append(f"{url}: broken {'image' if tag == 'img' else 'link'} → {link} (HTTP {c}).")
                elif "/sandbox/" in base_url and "/sandbox/" not in parts.path and tag in ("a", "img"):
                    warnings.append(f"{url}: {tag} {link} points to the live site instead of the sandbox.")

    report = {"blocking": blocking, "warnings": warnings, "spanish": spanish, "changes": changes, "notes": notes}
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for title, items in (("BLOCKING", blocking), ("WARNINGS", warnings), ("SPANISH", spanish), ("CHANGES", changes), ("NOTES", notes)):
            print(f"{title} ({len(items)})")
            for i in items:
                print(f"  - {i}")
        print("RESULT:", "NOT READY FOR A VOTE" if blocking else "OK TO VOTE (review warnings)")
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
