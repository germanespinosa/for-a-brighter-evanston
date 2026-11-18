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
import hashlib
import json
import os
import stat
import zipfile
import xml.etree.ElementTree as ET
import re
import subprocess
import sys
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
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
TEMPLATE_DIRS = ("_includes/", "_layouts/")
TEMPLATE_EXT = {".html", ".liquid", ".md", ".markdown"}
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
                value = m.group(2).strip()
                quoted = re.fullmatch(r'''('(?:[^']|'')*'|"(?:[^"\\]|\\.)*")(?:\s+#.*)?''', value)
                if quoted:
                    value = quoted.group(1)
                try:
                    value = json.loads(value)
                except (ValueError, TypeError):
                    if value.startswith("'") and value.endswith("'"):
                        value = value[1:-1].replace("''", "'")
                    elif (m.group(1) == "scripts" and re.fullmatch(
                            r"\[\s*(?:[A-Za-z0-9_.-]+\s*(?:,\s*[A-Za-z0-9_.-]+\s*)*)?\]", value)):
                        value = [item.strip() for item in value[1:-1].split(",") if item.strip()]
                    else:
                        value = re.split(r"\s+#", value, maxsplit=1)[0].strip()
                        # Do not turn YAML booleans, collections or complex
                        # values into apparently valid metadata strings.
                        if (not value or value.lower() in {"null", "~", "true", "false", "yes", "no", "on", "off"}
                                or value.startswith(('"', "'", "[", "{", "|", ">", "&", "*", "!"))
                                or re.fullmatch(r"[-+]?\d[\d.eExXa-fA-F_:+-]*", value)):
                            value = None
                data[m.group(1)] = value
    return data if isinstance(data, dict) else {}


def generic_share_images(base):
    """Reject both previous and current configured home fallbacks."""
    images = set()
    for lang in ("en", "es"):
        path = f"_data/i18n/{lang}.yml"
        current = ROOT / path
        for text in (git_show(base, path), current.read_text(encoding="utf-8") if current.is_file() else None):
            if text:
                # This also works without PyYAML; only the scalar is needed.
                for value in re.findall(r"^\s*share_image:\s*(.+)$", text, re.M):
                    image = parse_front_matter("share_image: " + value).get("share_image")
                    if isinstance(image, str):
                        images.add(image)
    return images


def share_image_problem(image, added_files, generic_images):
    if not isinstance(image, str) or not image.strip():
        return "must be a nonempty local image path for this page"
    if (not re.fullmatch(r"/assets/img/[A-Za-z0-9_./-]+", image)
            or any(part in ("", ".", "..") for part in image[1:].split("/"))
            or Path(image).suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}):
        return "must be a safe /assets/img/ JPG, JPEG, PNG or WebP path (no external URLs or traversal)"
    if image in generic_images:
        return "must be page-specific, not the generic home sharing card"
    path = image[1:]
    target = ROOT / path
    if any(p.is_symlink() for p in (target, *target.parents)) or not target.is_file():
        return "must refer to a regular local image file, not a missing file, directory or symlink"
    if path not in added_files or not git("ls-tree", "HEAD", "--", path).startswith(("100644 ", "100755 ")):
        return "must refer to an image tracked and added with this update, not a pre-existing asset"
    return None


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
        self.metadata = {}
        self.in_head = False
        self.iframes = []

    def handle_starttag(self, tag, attrs):
        if tag == "iframe":
            self.iframes.append(attrs)
        a = dict(attrs)
        if tag == "head":
            self.in_head = True
        if tag == "meta" and self.in_head:
            key = a.get("property") or a.get("name")
            if key:
                self.metadata.setdefault(key, []).append(a.get("content", ""))
        for attr in ("href", "src"):
            if a.get(attr) and tag in ("a", "img", "link", "script", "source"):
                self.links.append((tag, a[attr]))

    def handle_endtag(self, tag):
        if tag == "head":
            self.in_head = False

    handle_startendtag = handle_starttag


class DiscoveryParser(HTMLParser):
    """Collect approved sections as normalized HTML events and reject inert ancestors."""

    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self, marker=("aria-labelledby", "video-title")):
        super().__init__()
        self.marker = marker
        self.sections = []
        self.depth = 0
        self.ancestors = []
        self.inert = False

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        style = re.sub(r"\s+", "", values.get("style") or "").lower()
        hidden = (tag in {"template", "head", "noscript"} or "hidden" in values or "inert" in values
                  or (tag == "details" and "open" not in values)
                  or (values.get("aria-hidden") or "").lower() == "true"
                  or "display:none" in style or "visibility:hidden" in style)
        if not self.depth and tag == "section" and self.marker in attrs:
            self.sections.append([])
            self.depth = 1
            self.inert |= hidden or any(flag for _, flag in self.ancestors)
        elif self.depth and tag == "section":
            self.depth += 1
        if self.depth:
            self.sections[-1].append(("start", tag, tuple(sorted(attrs, key=repr))))
        if tag not in self.VOID:
            self.ancestors.append((tag, hidden))

    def handle_endtag(self, tag):
        if self.depth:
            self.sections[-1].append(("end", tag))
            if tag == "section":
                self.depth -= 1
        for index in range(len(self.ancestors) - 1, -1, -1):
            if self.ancestors[index][0] == tag:
                del self.ancestors[index:]
                break

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_data(self, data):
        text = " ".join(data.split())
        if self.depth and text:
            self.sections[-1].append(("text", text))


def expected_discovery(lang, base_url):
    template = (ROOT / "_includes/pages/home.html").read_text(encoding="utf-8")
    start, end = template.index(VIDEO_START.decode()), template.index(VIDEO_END.decode())
    section = template[start:end]
    conditional = re.search(r"{% if page.lang == 'es' %}(.*?){% else %}(.*?){% endif %}", section, re.S)
    arrow = re.search(r"{%- capture arrow -%}(.*?){%- endcapture -%}", template, re.S)
    if not conditional or not arrow:
        raise ValueError("approved video discovery template cannot be rendered")
    section = section[:conditional.start()] + conditional.group(1 if lang == "es" else 2) + section[conditional.end():]
    section = re.sub(r"{{ '(.*?)' \| relative_url }}",
                     lambda m: urlsplit(base_url).path + m.group(1).lstrip("/"), section)
    section = section.replace("{{ arrow }}", arrow.group(1))
    parser = DiscoveryParser()
    parser.feed(section)
    return parser.sections


class TemplateSafetyParser(HTMLParser):
    """Inspect source HTML without banning ordinary template Liquid or head tags."""

    def __init__(self):
        super().__init__()
        self.hazards = []

    def handle_starttag(self, tag, attrs):
        unsafe_tag = tag in {"script", "style", "iframe", "object", "embed",
                             "frame", "frameset", "applet", "form", "base"}
        unsafe_attr = any(
            name.startswith("on") or
            "javascript:" in re.sub(r"[\s\x00-\x20]+", "", value or "").lower()
            for name, value in attrs
        )
        if unsafe_tag or unsafe_attr:
            self.hazards.append(self.get_starttag_text())

    handle_startendtag = handle_starttag


def template_hazards(text):
    parser = TemplateSafetyParser()
    parser.feed(text)
    parser.close()
    # Compare whole script/style blocks, not counts of opening tags: replacing
    # a legacy script's body must not pass just because its tag stayed the same.
    blocks = re.finditer(r"<\s*(script|style)\b[^>]*>.*?(?:</\s*\1\s*>|\Z)",
                         text, re.I | re.S)
    return Counter(parser.hazards + [m.group(0) for m in blocks])


def fetch(url, method="GET", timeout=20):
    req = urllib.request.Request(url, method=method, headers={"User-Agent": "fabian-sandbox-check"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, (r.read().decode("utf-8", "replace") if method == "GET" else "")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:  # network errors
        return 0, str(e)


LINK_WORKERS = 16  # same-site link checks run this many at a time
LINK_TIMEOUT = 10


def link_status(url):
    """HTTP status of one same-site link (HEAD, falling back to GET on 405)."""
    c, _ = fetch(url, method="HEAD", timeout=LINK_TIMEOUT)
    if c == 405:
        c, _ = fetch(url, timeout=LINK_TIMEOUT)
    return c


def fetch_sharing_image(url):
    req = urllib.request.Request(url, headers={"User-Agent": "fabian-sandbox-check"})
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            mime = response.headers.get_content_type()
            return response.status, mime, bool(response.read(1))
    except urllib.error.HTTPError as error:
        return error.code, "", False
    except Exception:
        return 0, "", False


def fetch_approved_video_card(url, digest):
    """Fetch the complete bounded response; any network error or mismatch blocks."""
    req = urllib.request.Request(url, headers={"User-Agent": "fabian-sandbox-check"})
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            data = response.read(MEDIA_MAX_BYTES + 1)
            return (response.status == 200 and response.headers.get_content_type().startswith("image/")
                    and len(data) <= MEDIA_MAX_BYTES and hashlib.sha256(data).hexdigest() == digest)
    except Exception:
        return False


# These identity bindings enforce German's explicit same-class delegation;
# display names and content embedded in uploads are never authorization.
SCOPED_AUTHORIZERS = {"U0CE2G08ZRC", "U0CE4NY7KC2"}
SCOPED_CSS = {
    "assets/css/release-home.css": (["/", "/es/"], ".release-home"),
    "assets/css/release-poll.css": (["/home/voter-poll/", "/es/encuesta/"], ".release-poll"),
    "assets/css/release-path.css": (["/home/a-brighter-path-forward/", "/es/un-camino-mejor/"], ".release-path"),
}
SCOPED_WORKBOOK = "assets/files/d65-financial-model-v4.xlsx"


def load_scoped_approval(filename, sandbox_url=None):
    """Read an operator-created private record, never an uploaded authority claim."""
    if not filename:
        return {"css": [], "workbooks": []}
    path = Path(filename).absolute()
    root = ROOT.resolve()
    if any(p.is_symlink() for p in (path, *path.parents)) or path.resolve().is_relative_to(root):
        raise ValueError("approval must be a private non-symlink file outside the repository")
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("approval must be an operator-owned regular file with mode 0600 or stricter")
    record = json.loads(path.read_text(encoding="utf-8"))
    branch = git("branch", "--show-current").strip()
    sandbox = record.get("sandbox_id")
    if (record.get("version") != 1 or record.get("purpose") != "sandbox-review"
            or not isinstance(sandbox, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,39}", sandbox)
            or branch != "sandbox/" + sandbox):
        raise ValueError("approval purpose/version or sandbox branch does not match")
    if sandbox_url and (urlsplit(sandbox_url).scheme != "https" or
                        urlsplit(sandbox_url).netloc != "forabrighterevanston.org" or
                        urlsplit(sandbox_url).path.rstrip("/") != "/sandbox/" + sandbox):
        raise ValueError("approval sandbox does not match deployed URL")
    source = record.get("source", {})
    if (record.get("authorizer_id") not in SCOPED_AUTHORIZERS or
            source.get("channel_id") != "C0CEMKENSQ1" or
            not re.fullmatch(r"[0-9]+\.[0-9]{6}", str(source.get("message_ts", "")))):
        raise ValueError("approval needs an authorized human's original #website message provenance")
    css, workbooks = record.get("css"), record.get("workbooks")
    if not isinstance(css, list) or not isinstance(workbooks, list) or not (css or workbooks):
        raise ValueError("approval must list exact CSS or workbook assets")
    seen = set()
    for item in css:
        key = item.get("path")
        if key not in SCOPED_CSS or key in seen:
            raise ValueError("approval contains an unapproved or duplicate CSS path")
        if sandbox == "homepage-hero-heather" and key == "assets/css/release-home.css":
            raise ValueError("homepage hero CSS needs its separate reviewed hash-bound approval")
        routes, scope = SCOPED_CSS[key]
        if item.get("routes") != routes or item.get("scope") != scope:
            raise ValueError("approval CSS routes/scope do not match the exact permitted pages")
        seen.add(key)
    for item in workbooks:
        if (item.get("path") != SCOPED_WORKBOOK or item["path"] in seen or
                not re.fullmatch(r"[a-f0-9]{64}", str(item.get("sha256", "")))):
            raise ValueError("approval contains an unapproved workbook path or invalid SHA-256")
        seen.add(item["path"])
    return record


# Distinct German authorizations; neither grants general structural delegation.
MAINTENANCE_SOURCES = {
    "delegation-maintenance": "1794230153.839529",
    "poll-copy-maintenance": "1794242873.127109",
}
# This is deliberately independent of SCOPED_AUTHORIZERS and asset approvals.
MAINTENANCE_FILES = frozenset({
    "docs/agents/fabian-website.md", "docs/help/team-help.md",
    "docs/help/team-help.pdf", "docs/help/reviewed-sources.json",
    "scripts/sandbox_check.py", "scripts/tests/test_scoped_approval.py",
})


def load_maintenance_approval(filename, sandbox_url=None):
    """Validate a trusted private record against exact committed AND working bytes."""
    if not filename:
        return {}
    path = Path(filename).absolute()
    if (any(p.is_symlink() for p in (path, *path.parents))
            or path.resolve().is_relative_to(ROOT.resolve())):
        raise ValueError("maintenance approval must be a private non-symlink file outside the repository")
    # Validate the opened descriptor, not just a pathname stat before reading.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "r", encoding="utf-8") as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600):
            raise ValueError("maintenance approval must be operator-owned, regular and mode 0600")
        record = json.load(stream)
    if (not isinstance(record, dict)
            or set(record) != {"version", "purpose", "sandbox_id", "authorizer_id", "source", "files"}
            or type(record["version"]) is not int or record["version"] != 1
            or not isinstance(record["purpose"], str) or record["purpose"] not in MAINTENANCE_SOURCES
            or record["sandbox_id"] != "poll-model-release"
            or git("branch", "--show-current").strip() != "sandbox/poll-model-release"):
        raise ValueError("maintenance approval schema/purpose or exact sandbox branch does not match")
    if (record["authorizer_id"] != "U0CE2G08ZRC" or record["source"] != {
            "channel_id": "C0CEMKENSQ1", "message_ts": MAINTENANCE_SOURCES[record["purpose"]]}):
        raise ValueError("maintenance requires German's exact original #website authorization; Kerstin cannot approve it")
    if sandbox_url:
        url = urlsplit(sandbox_url)
        if (url.scheme != "https" or url.netloc != "forabrighterevanston.org"
                or url.path.rstrip("/") != "/sandbox/poll-model-release" or url.query or url.fragment):
            raise ValueError("maintenance approval sandbox does not match deployed URL")
    files = record["files"]
    approved = {}
    if not isinstance(files, list):
        raise ValueError("maintenance files must list the exact fixed inventory")
    for item in files:
        if (not isinstance(item, dict) or set(item) != {"path", "sha256"}
                or not isinstance(item["path"], str) or item["path"] not in MAINTENANCE_FILES
                or item["path"] in approved
                or not isinstance(item["sha256"], str)
                or not re.fullmatch(r"[a-f0-9]{64}", item["sha256"])):
            raise ValueError("maintenance contains invalid/duplicate file inventory or SHA-256")
        approved[item["path"]] = item["sha256"]
    if set(approved) != MAINTENANCE_FILES:
        raise ValueError("maintenance requires exactly the six reviewed files")
    for name, digest in approved.items():
        target = ROOT / name
        if (any(p.is_symlink() for p in (target, *target.parents)) or not target.is_file()
                or target.stat().st_mode & 0o111
                or not git("ls-tree", "HEAD", "--", name).startswith("100644 ")):
            raise ValueError(f"{name}: maintenance requires regular non-executable committed files; no deletions")
        committed = subprocess.run(["git", "-C", str(ROOT), "show", f"HEAD:{name}"],
                                   check=True, capture_output=True).stdout
        if (hashlib.sha256(committed).hexdigest() != digest
                or hashlib.sha256(target.read_bytes()).hexdigest() != digest):
            raise ValueError(f"{name}: maintenance SHA-256 must match both committed revision and working bytes")
    return approved


POLL_COPY_SCRIPT = "assets/js/poll-copy.js"
POLL_COPY_SHA256 = "e1ea7d637919e39bd28e4d67ccd7091a804832ab3658114695d504ebc7444d32"
POLL_COPY_PAGES = ["home/voter-poll/index.html", "es/encuesta/index.html"]
POLL_COPY_ROUTES = ["/home/voter-poll/", "/es/encuesta/"]


NOV16_PAGES = frozenset({
    "home/poll-results/index.html", "es/resultados-encuesta/index.html",
    "home/a-brighter-path-forward/index.html", "es/un-camino-mejor/index.html",
})
NOV16_MAINTENANCE_FILES = frozenset({
    "scripts/sandbox_check.py", "scripts/tests/test_page_deletion_approval.py",
    "docs/agents/fabian-website.md", "docs/agents/fabian-website-cards.md",
    "docs/help/team-help.md", "docs/help/team-help.pdf", "docs/help/reviewed-sources.json",
})
NOV16_PROVENANCE_DIGESTS = {
    "nov16-page-deletion": "d4588736ee5c89890031e4790ed1b86469fbe44e494f3c7783fb69c86a32730a",
    "nov16-checker-maintenance": "87fd6aace394248871cd3bf2d3af9ce9a5e3abcc567160dd973ed79997daf0c6",
}


def load_nov16_record(filename, purpose, base, sandbox_url):
    path = Path(filename).absolute()
    if (any(p.is_symlink() for p in (path, *path.parents))
            or path.resolve().is_relative_to(ROOT.resolve())):
        raise ValueError("approval must be a private non-symlink file outside the checkout")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "r", encoding="utf-8") as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600):
            raise ValueError("approval must be operator-owned, regular and mode 0600")
        record = json.load(stream, object_pairs_hook=unique_json_fields)
    keys = {"version", "purpose", "sandbox_id", "authorizer_id", "source",
            "checkout", "base_commit", "head_commit", "files"}
    if (not isinstance(record, dict) or set(record) != keys
            or type(record["version"]) is not int or record["version"] != 1
            or record["purpose"] != purpose or record["sandbox_id"] != "nov16-meeting"
            or not isinstance(record["authorizer_id"], str)
            or not isinstance(record["source"], dict)
            or set(record["source"]) != {"channel_id", "message_ts"}
            or not all(isinstance(value, str) for value in record["source"].values())
            or hashlib.sha256(json.dumps({"authorizer_id": record["authorizer_id"], "source": record["source"]},
                                         sort_keys=True, separators=(",", ":")).encode()).hexdigest()
               != NOV16_PROVENANCE_DIGESTS.get(purpose)
            or record["checkout"] != str(ROOT.resolve())
            or git("branch", "--show-current").strip() != "sandbox/nov16-meeting"
            or base != "origin/main"):
        raise ValueError("approval schema, source, checkout, base or sandbox does not match")
    base_commit = git("rev-parse", "--verify", "origin/main^{commit}").strip()
    head_commit = git("rev-parse", "--verify", "HEAD^{commit}").strip()
    if (record["base_commit"] != base_commit or record["head_commit"] != head_commit
            or git("merge-base", "origin/main", "HEAD").strip() != base_commit):
        raise ValueError("approval must bind the current base, HEAD and merge base")
    if sandbox_url:
        url = urlsplit(sandbox_url)
        if (url.scheme != "https" or url.netloc != "forabrighterevanston.org"
                or url.path.rstrip("/") != "/sandbox/nov16-meeting" or url.query or url.fragment):
            raise ValueError("approval sandbox does not match deployed URL")
    return record


def nov16_inventory(record, allowed):
    files = record["files"]
    approved = {}
    if not isinstance(files, list):
        raise ValueError("approval needs the exact file inventory")
    for item in files:
        if (not isinstance(item, dict) or set(item) != {"path", "sha256"}
                or not isinstance(item["path"], str) or item["path"] not in allowed
                or item["path"] in approved or not isinstance(item["sha256"], str)
                or not re.fullmatch(r"[a-f0-9]{64}", item["sha256"])):
            raise ValueError("invalid or duplicate approval inventory or SHA-256")
        approved[item["path"]] = item["sha256"]
    if set(approved) != allowed:
        raise ValueError("approval needs the exact file inventory")
    return approved


def load_nov16_deletion_approval(filename, base, sandbox_url):
    if not filename:
        return set()
    record = load_nov16_record(filename, "nov16-page-deletion", base, sandbox_url)
    approved = nov16_inventory(record, NOV16_PAGES)
    diff = git("diff", "--no-renames", "--name-status", "-z", "origin/main...HEAD").split("\0")
    entries = list(zip(diff[0::2], diff[1::2]))
    if {name for status, name in entries if status == "D"} != NOV16_PAGES:
        raise ValueError("approval requires exactly the four deletions, with no other deletions")
    if any((status, name) not in entries for name in NOV16_PAGES for status in ("D",)):
        raise ValueError("approved pages must be committed deletions")
    for name, digest in approved.items():
        target = ROOT / name
        if (any(p.is_symlink() for p in (target, *target.parents)) or os.path.lexists(target)
                or git("ls-tree", "HEAD", "--", name)
                or not git("ls-tree", "origin/main", "--", name).startswith("100644 ")
                or git("diff", "--cached", "--name-only", "HEAD", "--", name)):
            raise ValueError(f"{name}: expected a committed deletion with no staged or working reappearance")
        content = subprocess.run(["git", "-C", str(ROOT), "show", f"origin/main:{name}"],
                                 check=True, capture_output=True).stdout
        if hashlib.sha256(content).hexdigest() != digest:
            raise ValueError(f"{name}: base SHA-256 does not match")
    return set(approved)


def load_nov16_maintenance_approval(filename, base, sandbox_url):
    if not filename:
        return {}
    record = load_nov16_record(filename, "nov16-checker-maintenance", base, sandbox_url)
    approved = nov16_inventory(record, NOV16_MAINTENANCE_FILES)
    for name, digest in approved.items():
        target = ROOT / name
        base_mode = git("ls-tree", "origin/main", "--", name)
        if (any(p.is_symlink() for p in (target, *target.parents)) or not target.is_file()
                or target.stat().st_mode & 0o111
                or not git("ls-tree", "HEAD", "--", name).startswith("100644 ")
                or (base_mode and not base_mode.startswith("100644 "))
                or git("diff", "--cached", "--name-only", "HEAD", "--", name)):
            raise ValueError(f"{name}: maintenance requires unchanged-index regular non-executable files")
        committed = subprocess.run(["git", "-C", str(ROOT), "show", f"HEAD:{name}"],
                                   check=True, capture_output=True).stdout
        if (hashlib.sha256(committed).hexdigest() != digest
                or hashlib.sha256(target.read_bytes()).hexdigest() != digest):
            raise ValueError(f"{name}: maintenance SHA-256 must match committed and working bytes")
    return approved


# Separate provenance pins: content is not permission for process maintenance.
LETTER_VOTE_SOURCE_DIGEST = "c216bf944d4b60ba8f9c3cc12f71e619021f68cba249e547ff453e50c0d1aa30"
LETTER_VOTE_MAINTENANCE_SOURCE_DIGEST = "26ffb965db9260b8afff15da6faf7bc1da000b4aab1de5915da82038806a88c1"
LETTER_VOTE_BASE = "5b14e14d977916a937effef74dcc5cb91122efe3"
LETTER_VOTE_BASE_SHA256 = "090694a356a8020db6d7d5df48d22e180b2b5a51a3ce2db66caab83d8e695b32"
LETTER_VOTE_SCRIPT = "assets/js/letter-content.js"
LETTER_VOTE_MAINTENANCE = frozenset({
    "scripts/sandbox_check.py", "scripts/tests/test_letter_vote_approval.py",
    "docs/agents/fabian-website.md", "docs/agents/fabian-website-cards.md",
    "docs/help/team-help.md", "docs/help/team-help.pdf", "docs/help/reviewed-sources.json",
})
LETTER_VOTE_REPLACEMENTS = (
    ("D65 describes November 9 as a plan vote, with closure hearings and later final action still to follow.",
     "The board is expected to vote on the plan on November 16, with closure hearings and any final closure decision to follow."),
    ("El D65 describe la votación del 9 de noviembre como una votación sobre el plan, a la que todavía seguirían audiencias sobre los cierres y una decisión final posterior.",
     "Se espera que la Junta vote sobre el plan el 16 de noviembre; después seguirían audiencias sobre los cierres y cualquier decisión final al respecto."),
)
LETTER_VOTE_REMOVALS = (
    ("School Age Child Care (SACC)", "d51ce57e1172c061425a27c4b48e32a8752f818057da30bc2182bce83a0de979"),
    ("Cuidado infantil escolar (SACC)", "0baf9c04bf58bfa97b346079145b5b68efb4a1ce9ae5c3726006a31ff583d4a9"),
)


def load_letter_vote_approval(filename, purpose, base, sandbox_url):
    if not filename:
        return {}
    provenance = {
        "letter-vote-copy": ({"date", "delegation", "removal", "confirmation"}, LETTER_VOTE_SOURCE_DIGEST),
        "letter-vote-maintenance": ({"delegation", "maintenance"}, LETTER_VOTE_MAINTENANCE_SOURCE_DIGEST),
    }
    if purpose not in provenance:
        raise ValueError("unknown letter approval purpose")
    source_keys, source_digest = provenance[purpose]
    path = Path(filename).absolute()
    if (any(p.is_symlink() for p in (path, *path.parents))
            or path.resolve().is_relative_to(ROOT.resolve())):
        raise ValueError("letter approval must be a private non-symlink file outside the checkout")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "r", encoding="utf-8") as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600):
            raise ValueError("letter approval must be operator-owned, regular and mode 0600")
        record = json.load(stream, object_pairs_hook=unique_json_fields)
    keys = {"version", "purpose", "sandbox_id", "authorizer_id", "source", "checkout",
            "base_commit", "head_commit", "files"}
    if (not isinstance(record, dict) or set(record) != keys
            or type(record["version"]) is not int or record["version"] != 1
            or record["purpose"] != purpose or record["sandbox_id"] != "letter-vote-nov16"
            or not isinstance(record["authorizer_id"], str) or not isinstance(record["source"], dict)
            or set(record["source"]) != source_keys
            or hashlib.sha256(json.dumps({"authorizer_id": record["authorizer_id"], "source": record["source"]},
                                         sort_keys=True, separators=(",", ":")).encode()).hexdigest() != source_digest
            or record["checkout"] != str(ROOT.resolve())
            or git("branch", "--show-current").strip() != "sandbox/letter-vote-nov16"
            or base != "origin/main"):
        raise ValueError("letter approval schema, provenance, checkout, base or branch does not match")
    if (git("rev-parse", "--verify", "origin/main^{commit}").strip() != LETTER_VOTE_BASE
            or record["base_commit"] != LETTER_VOTE_BASE
            or record["head_commit"] != git("rev-parse", "--verify", "HEAD^{commit}").strip()
            or git("merge-base", "origin/main", "HEAD").strip() != LETTER_VOTE_BASE):
        raise ValueError("letter approval must bind the exact base, current HEAD and merge base")
    if sandbox_url:
        url = urlsplit(sandbox_url)
        if (url.scheme != "https" or url.netloc != "forabrighterevanston.org"
                or url.path.rstrip("/") != "/sandbox/letter-vote-nov16" or url.query or url.fragment):
            raise ValueError("letter approval sandbox URL does not match")
    allowed = {LETTER_VOTE_SCRIPT} if purpose == "letter-vote-copy" else LETTER_VOTE_MAINTENANCE
    approved = nov16_inventory(record, allowed)

    # Nothing else, even normally editable live data, was part of this consent.
    diff = git("diff", "--no-renames", "--name-status", "-z", "origin/main...HEAD").split("\0")
    entries = list(zip(diff[0::2], diff[1::2]))
    for status, name in entries:
        if (name == LETTER_VOTE_SCRIPT and status == "M"):
            continue
        if name in LETTER_VOTE_MAINTENANCE and (status == "M" or
                (name == "scripts/tests/test_letter_vote_approval.py" and status == "A")):
            continue
        raise ValueError(f"{name}: change outside letter vote authorization")
    if ("M", LETTER_VOTE_SCRIPT) not in entries:
        raise ValueError("letter approval requires the committed copy change")
    if git("status", "--porcelain=v1", "-z", "--untracked-files=all"):
        raise ValueError("letter approval requires a clean committed working tree and index")
    if any(not entry.startswith("H ") for entry in git("ls-files", "-v", "-z").split("\0") if entry):
        raise ValueError("letter approval forbids assume-unchanged and skip-worktree index entries")
    if git("ls-files", "--others", "--ignored", "--exclude-standard", "--", "assets/js/"):
        raise ValueError("letter approval forbids even ignored untracked assets/js files")
    for name, digest in approved.items():
        target = ROOT / name
        base_mode = git("ls-tree", "origin/main", "--", name)
        if (any(p.is_symlink() for p in (target, *target.parents)) or not target.is_file()
                or target.stat().st_mode & 0o111
                or not git("ls-tree", "HEAD", "--", name).startswith("100644 ")
                or (not base_mode and name != "scripts/tests/test_letter_vote_approval.py")
                or (base_mode and not base_mode.startswith("100644 "))):
            raise ValueError(f"{name}: expected regular non-executable committed file with valid base")
        committed = subprocess.run(["git", "-C", str(ROOT), "show", f"HEAD:{name}"],
                                   check=True, capture_output=True).stdout
        if hashlib.sha256(committed).hexdigest() != digest or target.read_bytes() != committed:
            raise ValueError(f"{name}: digest must match committed and working bytes")
        if name == LETTER_VOTE_SCRIPT:
            baseline = subprocess.run(["git", "-C", str(ROOT), "show", f"origin/main:{name}"],
                                      check=True, capture_output=True).stdout
            if hashlib.sha256(baseline).hexdigest() != LETTER_VOTE_BASE_SHA256:
                raise ValueError("letter script baseline SHA-256 mismatch")
            for before, after in LETTER_VOTE_REPLACEMENTS:
                before, after = before.encode(), after.encode()
                if baseline.count(before) != 1:
                    raise ValueError("letter script baseline substitution is not unique")
                baseline = baseline.replace(before, after, 1)
            for title, expected in LETTER_VOTE_REMOVALS:
                marker = b'      {\n        "title": "' + title.encode() + b'",'
                if baseline.count(marker) != 1:
                    raise ValueError("letter SACC removal marker is not unique")
                start = baseline.index(marker)
                ending = b'\n      },\n'
                end = baseline.index(ending, start) + len(ending)
                if hashlib.sha256(baseline[start:end]).hexdigest() != expected:
                    raise ValueError("letter SACC removal block SHA-256 mismatch")
                baseline = baseline[:start] + baseline[end:]
            if committed != baseline:
                raise ValueError("letter script must contain exactly the approved date substitutions and bilingual SACC removals")
    return approved


# This source digest must be filled only after independent verification of the
# human's original content and maintenance approvals. None fails closed.
HEARING_SOURCE_DIGEST = "6dd11e8bc87136a864c73061f4eb2552d4792d11877a05f52573275f3783a219"
HEARING_BASE = "8f27dc4f9639f11becba65876cb99148e823b66e"
HEARING_CANDIDATE = "ecf6122496fca1215afcc2751cdd6e6f04ccc579"
HEARING_SCRIPT = "assets/js/letter-content.js"
HEARING_CALENDAR = "d65-board-meeting.ics"
HEARING_MAINTENANCE = {
    "scripts/sandbox_check.py": "M",
    "scripts/tests/test_hearing_approval.py": "A",
    "docs/agents/fabian-website.md": "M",
    "docs/help/team-help.md": "M",
    "docs/help/team-help.pdf": "M",
    "docs/help/reviewed-sources.json": "M",
}


def load_hearing_approval(filename, base, sandbox_url):
    if not filename:
        return set()
    path = Path(filename).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)) or path.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError("hearing record must be a private non-symlink outside the checkout")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "r", encoding="utf-8") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError("hearing record must be operator-owned, regular and mode 0600")
        record = json.load(stream, object_pairs_hook=unique_json_fields)
    keys = {"version", "purpose", "sandbox_id", "source", "checkout", "base_commit",
            "candidate_commit", "head_commit", "files", "deleted"}
    if (not isinstance(record, dict) or set(record) != keys or type(record["version"]) is not int
            or record["version"] != 1 or record["purpose"] != "closure-hearings"
            or record["sandbox_id"] != "closure-hearings" or base != "origin/main"
            or record["checkout"] != str(ROOT.resolve())
            or git("branch", "--show-current").strip() != "sandbox/closure-hearings"
            or not isinstance(record["source"], dict)
            or set(record["source"]) != {"actor", "channel", "content_approval", "maintenance_approval"}
            or any(not isinstance(value, str) or not value.strip() for value in record["source"].values())
            or not isinstance(HEARING_SOURCE_DIGEST, str)
            or hashlib.sha256(json.dumps(record["source"], sort_keys=True, separators=(",", ":")).encode()).hexdigest() != HEARING_SOURCE_DIGEST):
        raise ValueError("hearing record schema, independently reviewed source, checkout or branch mismatch")
    if (record["base_commit"] != HEARING_BASE or record["candidate_commit"] != HEARING_CANDIDATE
            or git("rev-parse", "--verify", "origin/main^{commit}").strip() != HEARING_BASE
            or record["head_commit"] != git("rev-parse", "--verify", "HEAD^{commit}").strip()
            or git("merge-base", "origin/main", "HEAD").strip() != HEARING_BASE
            or git("merge-base", HEARING_CANDIDATE, "HEAD").strip() != HEARING_CANDIDATE):
        raise ValueError("hearing base, candidate, HEAD or ancestry mismatch")
    if sandbox_url:
        url = urlsplit(sandbox_url)
        if (url.scheme != "https" or url.netloc != "forabrighterevanston.org"
                or url.path.rstrip("/") != "/sandbox/closure-hearings" or url.query or url.fragment):
            raise ValueError("hearing sandbox URL mismatch")
    if git("status", "--porcelain=v1", "-z", "--untracked-files=all"):
        raise ValueError("hearing approval requires a clean committed worktree and index")
    if any(not entry.startswith("H ") for entry in git("ls-files", "-v", "-z").split("\0") if entry):
        raise ValueError("hearing approval forbids hidden index entries")
    diff = git("diff", "--no-renames", "--name-status", "-z", HEARING_CANDIDATE + "...HEAD").split("\0")
    entries = list(zip(diff[0::2], diff[1::2]))
    if any(HEARING_MAINTENANCE.get(name) != status for status, name in entries):
        raise ValueError("changes beyond the exact candidate and bounded maintenance are not authorized")
    if ("M", "scripts/sandbox_check.py") not in entries or ("A", "scripts/tests/test_hearing_approval.py") not in entries:
        raise ValueError("reviewed checker and its tests are required")
    allowed = {HEARING_SCRIPT} | {name for _, name in entries}
    approved = nov16_inventory(record, allowed)
    for name, digest in approved.items():
        target = ROOT / name
        if (any(p.is_symlink() for p in (target, *target.parents)) or not target.is_file()
                or target.stat().st_mode & 0o111
                or not git("ls-tree", "HEAD", "--", name).startswith("100644 ")):
            raise ValueError(f"{name}: expected regular non-executable committed file")
        committed = subprocess.run(["git", "-C", str(ROOT), "show", f"HEAD:{name}"],
                                   check=True, capture_output=True).stdout
        if hashlib.sha256(committed).hexdigest() != digest or target.read_bytes() != committed:
            raise ValueError(f"{name}: reviewed digest must match committed and working bytes")
    deleted = record["deleted"]
    if (not isinstance(deleted, dict) or set(deleted) != {"path", "base_sha256"}
            or deleted["path"] != HEARING_CALENDAR or not isinstance(deleted["base_sha256"], str)
            or not re.fullmatch(r"[a-f0-9]{64}", deleted["base_sha256"])):
        raise ValueError("hearing record must bind the exact deleted calendar and base digest")
    target = ROOT / HEARING_CALENDAR
    baseline = subprocess.run(["git", "-C", str(ROOT), "show", f"origin/main:{HEARING_CALENDAR}"],
                              check=True, capture_output=True).stdout
    if (any(p.is_symlink() for p in (target, *target.parents)) or os.path.lexists(target)
            or git("ls-tree", "HEAD", "--", HEARING_CALENDAR)
            or not git("ls-tree", "origin/main", "--", HEARING_CALENDAR).startswith("100644 ")
            or hashlib.sha256(baseline).hexdigest() != deleted["base_sha256"]):
        raise ValueError("hearing calendar deletion or base digest mismatch")
    return allowed | {HEARING_CALENDAR}


def unique_json_fields(pairs):
    record = {}
    for key, value in pairs:
        if key in record:
            raise ValueError("duplicate approval field: " + key)
        record[key] = value
    return record


# Preview-only: independently conveyed record digests are the trust boundary.
# Reviewers must verify private provenance and exact final candidate bytes.
# This policy check is not a security review or publication authorization.
MAILCHIMP_FILES = {"_includes/updates-dialog.html": "M", "assets/js/mailchimp-updates.js": "A"}
MAILCHIMP_MAINTENANCE = frozenset({
    "scripts/sandbox_check.py", "scripts/tests/test_mailchimp_script_approval.py",
    "docs/agents/fabian-website.md", "docs/agents/fabian-website-cards.md",
    "docs/help/team-help.md", "docs/help/team-help.pdf", "docs/help/reviewed-sources.json",
})
MAILCHIMP_PURPOSES = frozenset({"mailchimp-script-preview", "mailchimp-script-maintenance"})


def load_mailchimp_approval(filename, purpose, base, sandbox_url, review_sha256=None):
    """Bind exact record bytes to an independently conveyed review digest."""
    if not filename:
        if review_sha256:
            raise ValueError("Mailchimp review digest requires its approval record")
        return {}
    path = Path(filename).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)) or path.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError("Mailchimp approval must be outside checkout without symlinks")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError("Mailchimp approval must be operator-owned regular mode 0600")
        raw = stream.read()
    if (not isinstance(review_sha256, str) or not re.fullmatch(r"[a-f0-9]{64}", review_sha256)
            or hashlib.sha256(raw).hexdigest() != review_sha256):
        raise ValueError("Mailchimp requires an independently attested SHA-256 of the exact record bytes")
    record = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_json_fields)
    keys = {"version", "purpose", "sandbox_id", "authorizer_id", "source", "checkout", "base_commit", "head_commit", "files"}
    if (not isinstance(record, dict) or set(record) != keys or type(record["version"]) is not int
            or record["version"] != 1 or purpose not in MAILCHIMP_PURPOSES or record["purpose"] != purpose
            or record["sandbox_id"] != "mailchimp-script-preview"
            or not isinstance(record["authorizer_id"], str) or not re.fullmatch(r"U[A-Z0-9]+", record["authorizer_id"])
            or not isinstance(record["source"], dict)
            or set(record["source"]) != {"channel_id", "question_ts", "answer_ts"}
            or not isinstance(record["source"]["channel_id"], str)
            or not re.fullmatch(r"C[A-Z0-9]+", record["source"]["channel_id"])
            or any(not isinstance(record["source"][key], str) or not re.fullmatch(r"[0-9]+\.[0-9]{6}", record["source"][key])
                   for key in ("question_ts", "answer_ts"))
            or record["source"]["question_ts"] == record["source"]["answer_ts"]
            or record["checkout"] != str(ROOT.resolve()) or base != "origin/main"
            or git("branch", "--show-current").strip() != "sandbox/mailchimp-script-preview"):
        raise ValueError("Mailchimp record schema, provenance, checkout or branch mismatch")
    current_base = git("rev-parse", "--verify", "origin/main^{commit}").strip()
    head = git("rev-parse", "--verify", "HEAD^{commit}").strip()
    if (record["base_commit"] != current_base or record["head_commit"] != head
            or git("merge-base", "origin/main", "HEAD").strip() != current_base):
        raise ValueError("Mailchimp record must bind current base, HEAD and merge base")
    if sandbox_url:
        url = urlsplit(sandbox_url)
        if (url.scheme != "https" or url.netloc != "forabrighterevanston.org"
                or url.path.rstrip("/") != "/sandbox/mailchimp-script-preview" or url.query or url.fragment):
            raise ValueError("Mailchimp sandbox URL mismatch")
    if git("status", "--porcelain=v1", "-z", "--untracked-files=all"):
        raise ValueError("Mailchimp approval requires a clean committed worktree and index")
    if any(not item.startswith("H ") for item in git("ls-files", "-v", "-z").split("\0") if item):
        raise ValueError("Mailchimp approval forbids hidden index entries")
    if git("ls-files", "--others", "--ignored", "--exclude-standard", "-z"):
        raise ValueError("Mailchimp approval forbids all ignored untracked files in the checkout")
    diff = git("diff", "--no-renames", "--name-status", "-z", "origin/main...HEAD").split("\0")
    entries = list(zip(diff[0::2], diff[1::2]))
    actual = {name: status for status, name in entries}
    if len(actual) != len(entries) or any(actual.get(name) != status for name, status in MAILCHIMP_FILES.items()):
        raise ValueError("Mailchimp behavior change inventory mismatch")
    maintenance = {name: status for status, name in entries if name in MAILCHIMP_MAINTENANCE}
    if (maintenance.get("scripts/sandbox_check.py") != "M"
            or maintenance.get("scripts/tests/test_mailchimp_script_approval.py") != "A"
            or any(status not in {"A", "M"} for status in maintenance.values())
            or actual != {**MAILCHIMP_FILES, **maintenance}):
        raise ValueError("Mailchimp candidate contains missing or unauthorized maintenance or other changes")
    expected = set(MAILCHIMP_FILES if purpose == "mailchimp-script-preview" else maintenance)
    files = record["files"]
    if not isinstance(files, list):
        raise ValueError("Mailchimp approval needs an exact file inventory")
    approved = {}
    for item in files:
        if (not isinstance(item, dict) or set(item) != {"path", "mode", "working_mode", "sha256"}
                or not isinstance(item["path"], str) or item["path"] not in expected
                or item["path"] in approved or item["mode"] != "100644"
                or not isinstance(item["working_mode"], str) or not re.fullmatch(r"0[0-7]{3}", item["working_mode"])
                or int(item["working_mode"], 8) & 0o133
                or not isinstance(item["sha256"], str) or not re.fullmatch(r"[a-f0-9]{64}", item["sha256"])):
            raise ValueError("invalid or duplicate Mailchimp file inventory")
        approved[item["path"]] = (item["sha256"], int(item["working_mode"], 8))
    if set(approved) != expected:
        raise ValueError("Mailchimp approval needs the exact file inventory")
    for name, (digest, working_mode) in approved.items():
        target = ROOT / name
        baseline = git("ls-tree", "origin/main", "--", name)
        if (any(p.is_symlink() for p in (target, *target.parents)) or not target.is_file()
                or stat.S_IMODE(target.stat().st_mode) != working_mode
                or not git("ls-tree", "HEAD", "--", name).startswith("100644 ")
                or (baseline and not baseline.startswith("100644 "))):
            raise ValueError(f"{name}: expected committed and working regular mode 100644")
        committed = subprocess.run(["git", "-C", str(ROOT), "show", f"HEAD:{name}"],
                                   check=True, capture_output=True).stdout
        if hashlib.sha256(committed).hexdigest() != digest or target.read_bytes() != committed:
            raise ValueError(f"{name}: reviewed digest must match committed and working bytes")
    return approved


HERO_CSS = "assets/css/release-home.css"
HERO_SCRIPT = "assets/js/hero-slideshow.js"
HERO_SOURCE_SHA256 = "7b61ae81b9bd7f6a7cecc23f8a8f6c58a4fb1ebbc7e46fffc0499ca4f6e41643"
HERO_PUBLICATION_SOURCE_SHA256 = "c99b405655561a1af8a7ecbb0afa2fbe116bc1151ab567e00edcd36bc6defa71"
HERO_BASE_COMMIT = "09a9d89b86586e9779454fcdb4911bda62dd03f9"
HERO_AUTHORIZATION_HEAD = "fa6b193ea35c2bface8ddf90074208bd6720f93e"
HERO_TEMPLATE = "_includes/pages/home.html"
HERO_TEMPLATE_BASE_SHA256 = "f74d592ded8bfa7196061e8044040c86171f7d65118a145ea794d1212657c762"
HERO_TEMPLATE_SHA256 = "b183e0c0d4c36016a195709273bdc387153c4aed59230cab9a8dd2162d1463e8"
HERO_DATA = "_data/hero.yml"
HERO_DATA_SHA256 = "46f404c057fe2faf2ad9190734006a236654e651cf8257305ef0ef69dd85ecad"
# Supplied prepared-manifest hashes; changing these requires independent review.
HERO_PHOTO_SHA256 = {
    "assets/img/hero/heather-eidson-meetup-01.jpg": "99cd6be7fc893dcbff422c11e34d011823017f6b1932911aea501860b66fef29",
    "assets/img/hero/heather-eidson-meetup-02.jpg": "ee6551ec55a55b2a17ece23c2a9f8191d1175c771433e5c27251e7fdffc2f913",
    "assets/img/hero/heather-eidson-meetup-03.jpg": "c1623e1bd8efeb5dc5c1402888bce134f362d61668bd9493a2aecb901ac02f58",
    "assets/img/hero/heather-eidson-meetup-04.jpg": "5fa69917710f58ef552a5dd5c2fdf254dc8a13632e4b9be342668a8c8cdf942a",
    "assets/img/hero/heather-eidson-meetup-05.jpg": "a5964e4b5559d704c22f38f28c68dd03c0ea1841467be20299cd87b7cb917ed8",
    "assets/img/hero/heather-eidson-meetup-06.jpg": "2351890bf401c1f4066d413669bfad8e83682458678e6090aaff06fa7f9bf56f",
    "assets/img/hero/heather-eidson-meetup-07.jpg": "8d04500a427513b1f7cc5cb7b3aae2a4e018829ab003929f12ec5491aa61c0cf",
    "assets/img/hero/heather-eidson-meetup-08.jpg": "01b7ceaf333a501ea3d99acb550ebd99f338c9a67a84a2f8cf87e3e192b744e4",
    "assets/img/hero/heather-eidson-meetup-09.jpg": "f4a232facbc5297a5556a1b1a947d3ac8ad9a99608ae675addc48edc81a591e1",
    "assets/img/hero/heather-eidson-meetup-10.jpg": "f1cf0c8d9aa8c5b304f1e7f0ca2876f1285b39d1eef7daf36283951698d983c7",
}
HERO_REVIEWED_SHA256 = {
    HERO_CSS: "ba6e19296d74cedd93468847b89538cf7fa0e61d37ee683d3af17ff4fdb87a2c",
    HERO_SCRIPT: "3963b9f166e4a22dcac0aa9410a3366279889257d9dcf2c32cb6532b797fd92a",
}
HERO_PAGES = ["index.html", "es/index.html"]
HERO_ROUTES = ["/", "/es/"]
HERO_OLD_LINK = "  {%- if page.url == '/home/voter-poll/' or page.url == '/es/encuesta/' %}\n"
HERO_NEW_LINK = ("  {%- if page.url == '/' or page.url == '/es/' %}\n"
                 "  <link rel=\"stylesheet\" href=\"{{ '/assets/css/release-home.css' | relative_url }}\">\n"
                 "  {%- elsif page.url == '/home/voter-poll/' or page.url == '/es/encuesta/' %}\n")
HERO_OLD_BODY = "{% if page.url == '/home/voter-poll/' or page.url == '/es/encuesta/' %} release-poll"
HERO_NEW_BODY = "{% if page.url == '/' or page.url == '/es/' %} release-home{% elsif page.url == '/home/voter-poll/' or page.url == '/es/encuesta/' %} release-poll"
HERO_MAINTENANCE = frozenset({
    "scripts/sandbox_check.py", "scripts/tests/test_homepage_hero_approval.py", "scripts/tests/test_hero_slideshow.py",
    "docs/agents/fabian-website.md", "docs/agents/fabian-website-cards.md",
    "docs/help/team-help.md", "docs/help/team-help.pdf", "docs/help/reviewed-sources.json",
})
# Fail closed until an independent review of the final non-checker inventory.
# The source manifest refers back to this checker, so pin its other entries
# canonically and bind its exact bytes via the separately attested record.
HERO_MAINTENANCE_INVENTORY_SHA256 = "4473e1763738e3c7059b16691fa570fa99682720f2f78fdead1bc8841443dff1"

# This is the exact original human approval record, not a new approval or vote.
VIDEO_APPROVAL_SHA256 = "e2881eb4e9f724f69290d033ae9bf5efef9e50ace29f0f1435b175b09075a30f"
VIDEO_SOURCE_SHA256 = "beebcaf5faf1610228ad02fd04622426a31aecf02f1177a8ae565a7a918bcc7a"
VIDEO_CHECKOUT = "/home/german/fabian-workspaces/homepage-hero-heather"
VIDEO_AUTHORIZATION_HEAD = "959fa91be86ad0fe5feb852dda21469bde323fad"
VIDEO_TEMPLATE_SHA256 = "2f8e069bf9b3d2f14d37f9c825b001a1efcbf0b8dee3a9956d709a37f65b03eb"
VIDEO_FILES = {
    "home/video/index.html": "6e7dc095d395300bcc19230ae4ae9010dc54b0ec910051dca6eb3133a90be267",
    "es/video/index.html": "d56fa9c2c2a2fbdb776248ec7ecc5dc5dcbec51cbf15b80053efcd629248f5ff",
    "assets/img/share-video-en.png": "9718c494e5974ca12d9a797d15e51fca696ce302c62c439548844f130934d8a6",
    "assets/img/share-video-es.png": "fe86fa77a6821803c231694cc44b58471c9297fc8c5db4690e9f8bb07986b7cd",
}
VIDEO_START = b'<section class="hm-section hm-section--white" aria-labelledby="video-title">'
VIDEO_END = b'<section class="hm-section hm-section--cream" id="the-problem"'


def load_youtube_approval(filename, base, sandbox_url):
    if not filename:
        return False
    path = Path(filename).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)) or path.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError("YouTube approval must be outside checkout with no symlinks")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError("YouTube approval must be operator-owned regular mode 0600")
        raw = stream.read()
    if hashlib.sha256(raw).hexdigest() != VIDEO_APPROVAL_SHA256:
        raise ValueError("YouTube approval bytes differ from the verified original provenance")
    record = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_json_fields)
    source_keys = {"channel_id", "authorizer_id", "question_ts", "answer_ts", "answer"}
    keys = source_keys | {"purpose", "video_url", "video_id", "scope"}
    if (not isinstance(record, dict) or set(record) != keys
            or not all(isinstance(record[key], str) for key in keys)
            or record["purpose"] != "youtube-embed-exception-for-video-preview-and-safety-checks"
            or record["video_url"] != "https://youtu.be/EMAzDgqHdYI"
            or record["video_id"] != "EMAzDgqHdYI"
            or record["scope"] != "Only this video’s YouTube player and necessary safety checks; preserve hero and normal team vote. No approval to bypass vote."
            or hashlib.sha256(json.dumps({key: record[key] for key in source_keys}, sort_keys=True,
                                         separators=(",", ":")).encode()).hexdigest() != VIDEO_SOURCE_SHA256
            or str(ROOT.resolve()) != VIDEO_CHECKOUT or base != "origin/main"):
        raise ValueError("YouTube approval schema, provenance or exact checkout mismatch")
    if (git("branch", "--show-current").strip() != "sandbox/homepage-hero-heather"
            or git("rev-parse", "origin/main^{commit}").strip() != HERO_BASE_COMMIT
            or git("merge-base", "origin/main", "HEAD").strip() != HERO_BASE_COMMIT
            or subprocess.run(["git", "-C", str(ROOT), "merge-base", "--is-ancestor",
                               VIDEO_AUTHORIZATION_HEAD, "HEAD"], capture_output=True).returncode):
        raise ValueError("YouTube approval branch, base or authorization HEAD mismatch")
    if sandbox_url:
        url = urlsplit(sandbox_url)
        if (url.scheme != "https" or url.netloc != "forabrighterevanston.org"
                or url.path.rstrip("/") != "/sandbox/homepage-hero-heather" or url.query or url.fragment):
            raise ValueError("YouTube approval sandbox URL mismatch")
    for name, digest in VIDEO_FILES.items():
        target = ROOT / name
        if (any(p.is_symlink() for p in (target, *target.parents)) or not target.is_file()
                or target.stat().st_mode & 0o111 or target.stat().st_size > MEDIA_MAX_BYTES
                or not git("ls-tree", "HEAD", "--", name).startswith("100644 ")
                or git("ls-tree", "origin/main", "--", name)):
            raise ValueError(f"{name}: approved video file must be a new regular file")
        committed = subprocess.run(["git", "-C", str(ROOT), "show", f"HEAD:{name}"],
                                   check=True, capture_output=True).stdout
        if hashlib.sha256(committed).hexdigest() != digest or target.read_bytes() != committed:
            raise ValueError(f"{name}: video file differs from the exact approved bytes")
    return True


def load_homepage_hero_approval(filename, purpose, base, sandbox_url, review_sha256=None, video=False):
    """Trusted, independently reviewed hashes; never infer approval from assets."""
    if not filename:
        return {}
    path = Path(filename).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)) or path.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError("hero approval must be a private non-symlink file outside the checkout")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError("hero approval must be operator-owned, regular and mode 0600")
        raw = stream.read()
        if purpose == "homepage-hero-maintenance":
            if (not isinstance(review_sha256, str) or not re.fullmatch(r"[a-f0-9]{64}", review_sha256)
                    or hashlib.sha256(raw).hexdigest() != review_sha256):
                raise ValueError("maintenance needs the independently reviewed record SHA-256")
        record = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_json_fields)
    keys = {"version", "purpose", "sandbox_id", "authorizer_id", "source", "checkout",
            "base_commit", "head_commit", "pages", "routes", "scope", "files"}
    if (not isinstance(record, dict) or set(record) != keys or type(record["version"]) is not int
            or record["version"] != 1 or record["purpose"] != purpose
            or purpose not in {"homepage-hero-assets", "homepage-hero-maintenance"}
            or record["sandbox_id"] != "homepage-hero-heather"
            or not isinstance(record["authorizer_id"], str) or not isinstance(record["source"], dict)
            or set(record["source"]) != {"channel_id", "message_ts", "question_ts"}
            or not all(isinstance(value, str) for value in record["source"].values())
            or hashlib.sha256(json.dumps({"authorizer_id": record["authorizer_id"], "source": record["source"]},
                                        sort_keys=True, separators=(",", ":")).encode()).hexdigest() != HERO_SOURCE_SHA256
            or record["checkout"] != str(ROOT.resolve()) or base != "origin/main"
            or git("branch", "--show-current").strip() != "sandbox/homepage-hero-heather"
            or record["pages"] != HERO_PAGES or record["routes"] != HERO_ROUTES
            or record["scope"] != ".release-home"):
        raise ValueError("hero approval schema, provenance, scope, checkout or sandbox does not match")
    current_base = git("rev-parse", "--verify", "origin/main^{commit}").strip()
    if (current_base != HERO_BASE_COMMIT or record["base_commit"] != current_base or record["head_commit"] != git("rev-parse", "HEAD^{commit}").strip()
            or git("merge-base", "origin/main", "HEAD").strip() != current_base):
        raise ValueError("hero approval must bind current base, HEAD and merge base")
    if git("status", "--porcelain=v1", "-z", "--untracked-files=all"):
        raise ValueError("hero approval requires a clean committed checkout and index")
    if any(not entry.startswith("H ") for entry in git("ls-files", "-v", "-z").split("\0") if entry):
        raise ValueError("hero approval forbids hidden index entries")
    if git("ls-files", "--others", "--ignored", "--exclude-standard", "--", "assets/js/"):
        raise ValueError("hero approval forbids ignored untracked scripts")
    if git("ls-files", "--others", "--ignored", "--exclude-standard", "--", *MEDIA_DIRS):
        raise ValueError("hero approval forbids ignored untracked media")
    if sandbox_url:
        url = urlsplit(sandbox_url)
        if (url.scheme != "https" or url.netloc != "forabrighterevanston.org"
                or url.path.rstrip("/") != "/sandbox/homepage-hero-heather" or url.query or url.fragment):
            raise ValueError("hero approval sandbox URL does not match")
    allowed = frozenset({HERO_CSS, HERO_SCRIPT}) if purpose == "homepage-hero-assets" else HERO_MAINTENANCE
    approved = nov16_inventory(record, allowed)
    if purpose == "homepage-hero-maintenance":
        independent_inventory = {name: digest for name, digest in approved.items()
                                 if name != "scripts/sandbox_check.py"}
        manifest_path = ROOT / "docs/help/reviewed-sources.json"
        if any(p.is_symlink() for p in (manifest_path, *manifest_path.parents)) or not manifest_path.is_file():
            raise ValueError("maintenance source manifest must be a regular file")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"), object_pairs_hook=unique_json_fields)
        if (not isinstance(manifest, dict)
                or manifest.pop("scripts/sandbox_check.py", None) != approved["scripts/sandbox_check.py"]):
            raise ValueError("maintenance source manifest must bind the approved checker SHA-256")
        independent_inventory["docs/help/reviewed-sources.json"] = hashlib.sha256(
            json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        inventory_digest = hashlib.sha256(json.dumps(independent_inventory, sort_keys=True,
                                                     separators=(",", ":")).encode()).hexdigest()
        if inventory_digest != HERO_MAINTENANCE_INVENTORY_SHA256:
            raise ValueError("maintenance requires the independently pinned maintenance inventory")
    if purpose == "homepage-hero-assets":
        if approved != HERO_REVIEWED_SHA256:
            raise ValueError("hero asset hashes must match the independently reviewed pinned bytes")
        for name, digest in ((HERO_TEMPLATE, HERO_TEMPLATE_SHA256), (HERO_DATA, HERO_DATA_SHA256)):
            target = ROOT / name
            if (any(p.is_symlink() for p in (target, *target.parents)) or not target.is_file()
                    or target.stat().st_mode & 0o111
                    or not git("ls-tree", "HEAD", "--", name).startswith("100644 ")
                    or not git("ls-tree", "origin/main", "--", name).startswith("100644 ")):
                raise ValueError(f"{name}: reviewed hero input must be a regular existing file")
            content = subprocess.run(["git", "-C", str(ROOT), "show", f"HEAD:{name}"],
                                     check=True, capture_output=True).stdout
            if name == HERO_TEMPLATE and video:
                if (hashlib.sha256(content).hexdigest() != VIDEO_TEMPLATE_SHA256
                        or content.count(VIDEO_START) != 1 or content.count(VIDEO_END) != 1):
                    raise ValueError("video discovery template differs from approved bytes")
                start, end = content.index(VIDEO_START), content.index(VIDEO_END)
                if end <= start or hashlib.sha256(content[:start] + content[end:]).hexdigest() != digest:
                    raise ValueError("video discovery must preserve the entire reviewed hero template")
            elif hashlib.sha256(content).hexdigest() != digest:
                raise ValueError(f"{name}: hero input must match independently reviewed exact bytes")
            if target.read_bytes() != content:
                raise ValueError(f"{name}: hero input must match independently reviewed exact bytes")
        # Parse a deliberately narrow YAML subset identically with and without PyYAML.
        # Reject extra keys, aliases, foreign paths, duplicates and unsafe CSS values.
        try:
            lines = [line for line in (ROOT / HERO_DATA).read_text(encoding="ascii").splitlines()
                     if line and not line.startswith("#")]
        except UnicodeError as error:
            raise ValueError("hero photo records must use the strict ASCII format") from error
        if len(lines) != 4 * len(HERO_PHOTO_SHA256):
            raise ValueError("hero photo records must contain exactly the approved inventory")
        names = []
        for offset in range(0, len(lines), 4):
            file = re.fullmatch(r"- file: (heather-eidson-meetup-[0-9]{2}\.jpg)", lines[offset])
            # CSS has exact attribute selectors for canonical 0% through 100%.
            position = re.fullmatch(r'  position: "(0|[1-9][0-9]?|100)% (0|[1-9][0-9]?|100)%"', lines[offset + 1])
            width = re.fullmatch(r"  width: ([1-9][0-9]{0,3})", lines[offset + 2])
            height = re.fullmatch(r"  height: ([1-9][0-9]{0,3})", lines[offset + 3])
            if (not file or not position or not width or not height
                    or any(int(value) > 100 for value in position.groups())
                    or int(width.group(1)) > 1600 or int(height.group(1)) > 1600):
                raise ValueError("hero photo record has unsafe file, position or dimensions")
            names.append("assets/img/hero/" + file.group(1))
        if names != list(HERO_PHOTO_SHA256):
            raise ValueError("hero photo records must list the approved local files in order")
        for lang, old_credit, new_credit in (
                ("en", b"  photo_credit: Photo by Joerg Metzner\n", b"  photo_credit: Photos by Heather Eidson\n"),
                ("es", b"  photo_credit: Foto de Joerg Metzner\n", b"  photo_credit: Fotos de Heather Eidson\n")):
            name = f"_data/i18n/{lang}.yml"
            original = subprocess.run(["git", "-C", str(ROOT), "show", f"origin/main:{name}"],
                                      check=True, capture_output=True).stdout
            current = subprocess.run(["git", "-C", str(ROOT), "show", f"HEAD:{name}"],
                                     check=True, capture_output=True).stdout
            target = ROOT / name
            if (original.count(old_credit) != 1 or current != original.replace(old_credit, new_credit, 1)
                    or any(p.is_symlink() for p in (target, *target.parents)) or not target.is_file()
                    or target.stat().st_mode & 0o111
                    or not git("ls-tree", "HEAD", "--", name).startswith("100644 ")
                    or not git("ls-tree", "origin/main", "--", name).startswith("100644 ")
                    or target.read_bytes() != current):
                raise ValueError(f"{name}: homepage translation must match base except the exact photo credit")
        original_template = subprocess.run(["git", "-C", str(ROOT), "show", f"origin/main:{HERO_TEMPLATE}"],
                                           check=True, capture_output=True).stdout
        if hashlib.sha256(original_template).hexdigest() != HERO_TEMPLATE_BASE_SHA256:
            raise ValueError("hero template baseline differs from reviewed current main")
        layout = git_show("origin/main", "_layouts/default.html")
        if (layout is None or layout.count(HERO_OLD_LINK) != 1 or layout.count(HERO_OLD_BODY) != 1
                or git_show("HEAD", "_layouts/default.html") != layout.replace(HERO_OLD_LINK, HERO_NEW_LINK, 1).replace(HERO_OLD_BODY, HERO_NEW_BODY, 1)):
            raise ValueError("hero stylesheet/wrapper requires the exact two-route layout change and no other layout edits")
        diff = git("diff", "--no-renames", "--name-status", "-z", "origin/main...HEAD").split("\0")
        entries = list(zip(diff[0::2], diff[1::2]))
        images = {name: status for status, name in entries if name.startswith(MEDIA_DIRS)}
        expected_images = {name: "A" for name in HERO_PHOTO_SHA256}
        if video:
            expected_images.update({name: "A" for name in VIDEO_FILES if name.startswith(MEDIA_DIRS)})
        if images != expected_images:
            raise ValueError("hero photo image change inventory must be exactly the ten approved additions")
        for name, digest in HERO_PHOTO_SHA256.items():
            target = ROOT / name
            if (any(p.is_symlink() for p in (target, *target.parents)) or not target.is_file()
                    or target.stat().st_mode & 0o111 or target.stat().st_size > MEDIA_MAX_BYTES
                    or not git("ls-tree", "HEAD", "--", name).startswith("100644 ")
                    or git("ls-tree", "origin/main", "--", name)):
                raise ValueError(f"{name}: approved photo must be a new regular non-executable file")
            committed = subprocess.run(["git", "-C", str(ROOT), "show", f"HEAD:{name}"],
                                       check=True, capture_output=True).stdout
            if hashlib.sha256(committed).hexdigest() != digest or target.read_bytes() != committed:
                raise ValueError(f"{name}: photo must match the supplied pinned bytes")
        for status, name in entries:
            if name.startswith(TEMPLATE_DIRS) and name not in {"_layouts/default.html", "_includes/pages/home.html"}:
                raise ValueError(f"{name}: other template changes require separate review")
        for name, route in zip(HERO_PAGES, HERO_ROUTES):
            original_bytes = subprocess.run(["git", "-C", str(ROOT), "show", f"origin/main:{name}"],
                                            check=True, capture_output=True).stdout
            current_bytes = subprocess.run(["git", "-C", str(ROOT), "show", f"HEAD:{name}"],
                                           check=True, capture_output=True).stdout
            loader = b"scripts: [home.js]\n"
            new_loader = b"scripts: [home.js, hero-slideshow.js]\n"
            target = ROOT / name
            if (original_bytes.count(loader) != 1 or not original_bytes.startswith(b"---\n")
                    or loader not in original_bytes.split(b"\n---\n", 1)[0] + b"\n"
                    or current_bytes != original_bytes.replace(loader, new_loader, 1)
                    or any(p.is_symlink() for p in (target, *target.parents))
                    or not target.is_file() or target.stat().st_mode & 0o111
                    or not git("ls-tree", "HEAD", "--", name).startswith("100644 ")
                    or not git("ls-tree", "origin/main", "--", name).startswith("100644 ")
                    or target.read_bytes() != current_bytes):
                raise ValueError(f"{name}: homepage must match base bytes except the exact approved loader")
            original = git_show("origin/main", name)
            current = git_show("HEAD", name)
            if original is None or current is None:
                raise ValueError("both existing homepage loaders are required")
            old = parse_front_matter(split_front_matter(original)[0])
            new = parse_front_matter(split_front_matter(current)[0])
            if (not isinstance(old.get("scripts"), list) or new.get("scripts") != old["scripts"] + ["hero-slideshow.js"]
                    or page_url(name, new) != route):
                raise ValueError("hero script must load exactly once on both approved homepage routes")
    for name, digest in approved.items():
        target = ROOT / name
        baseline = git("ls-tree", "origin/main", "--", name)
        if (any(p.is_symlink() for p in (target, *target.parents)) or not target.is_file()
                or target.stat().st_mode & 0o111
                or not git("ls-tree", "HEAD", "--", name).startswith("100644 ")
                or (baseline and not baseline.startswith("100644 "))
                or (name == HERO_SCRIPT and baseline)
                or git("diff", "--cached", "--name-only", "HEAD", "--", name)):
            raise ValueError(f"{name}: requires regular non-executable committed and unstaged file")
        committed = subprocess.run(["git", "-C", str(ROOT), "show", f"HEAD:{name}"],
                                   check=True, capture_output=True).stdout
        if hashlib.sha256(committed).hexdigest() != digest or target.read_bytes() != committed:
            raise ValueError(f"{name}: reviewed hash must match committed and working bytes")
        if name == HERO_CSS:
            problem = scoped_css_problem(committed.decode("utf-8"), ".release-home")
            if problem or len(committed) > MEDIA_MAX_BYTES:
                raise ValueError(f"{name}: {problem or 'CSS exceeds 5 MB'}")
    # Compare the entire candidate tree to the pinned merged main, not just
    # media/templates or paths covered by the two approval records.  Normal
    # editable content is not a separate authorization for this exception.
    additions = {HERO_SCRIPT, *HERO_PHOTO_SHA256,
                 "scripts/tests/test_homepage_hero_approval.py", "scripts/tests/test_hero_slideshow.py"}
    if video:
        additions.update(VIDEO_FILES)
    modifications = {HERO_CSS, HERO_TEMPLATE, HERO_DATA, "_layouts/default.html",
                     "_data/i18n/en.yml", "_data/i18n/es.yml", *HERO_PAGES,
                     *(HERO_MAINTENANCE - additions)}
    expected = {**{name: "A" for name in additions}, **{name: "M" for name in modifications}}
    diff = git("diff", "--no-renames", "--name-status", "-z", "origin/main...HEAD").split("\0")
    entries = list(zip(diff[0::2], diff[1::2]))
    actual = {name: status for status, name in entries}
    if len(actual) != len(entries) or actual != expected:
        unexpected = sorted(name for name, status in actual.items() if expected.get(name) != status)
        missing = sorted(name for name, status in expected.items() if actual.get(name) != status)
        raise ValueError(f"hero candidate changed-path inventory mismatch: unexpected/status {unexpected}; missing/status {missing}")
    return approved


def load_hero_publication_safeguards(filename, review_sha256, base, assets, maintenance):
    """Distinct user authorization and independently attested record, not a vote."""
    if not filename:
        if review_sha256:
            raise ValueError("publication review digest without record")
        return False
    if not assets or not maintenance:
        raise ValueError("both original preview approvals are required")
    path = Path(filename).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)) or path.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError("publication record must be outside checkout without symlinks")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError("publication record must be operator-owned regular mode 0600")
        raw = stream.read()
    if (not isinstance(review_sha256, str) or not re.fullmatch(r"[a-f0-9]{64}", review_sha256)
            or hashlib.sha256(raw).hexdigest() != review_sha256):
        raise ValueError("publication requires independently attested record SHA-256")
    record = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_json_fields)
    keys = {"version", "purpose", "sandbox_id", "authorizer_id", "source", "authorization_head",
            "checkout", "base_commit", "head_commit", "pages", "routes", "scope", "files"}
    if (not isinstance(record, dict) or set(record) != keys or type(record["version"]) is not int
            or record["version"] != 1 or record["purpose"] != "homepage-hero-publication-safeguards"
            or record["sandbox_id"] != "homepage-hero-heather"
            or hashlib.sha256(json.dumps({"authorizer_id": record["authorizer_id"], "source": record["source"]},
                                         sort_keys=True, separators=(",", ":")).encode()).hexdigest() != HERO_PUBLICATION_SOURCE_SHA256
            or record["authorization_head"] != HERO_AUTHORIZATION_HEAD
            or record["checkout"] != str(ROOT.resolve()) or base != "origin/main"
            or record["base_commit"] != HERO_BASE_COMMIT
            or record["head_commit"] != git("rev-parse", "HEAD^{commit}").strip()
            or record["pages"] != HERO_PAGES or record["routes"] != HERO_ROUTES
            or record["scope"] != ".release-home"):
        raise ValueError("publication record schema, provenance or binding mismatch")
    if subprocess.run(["git", "-C", str(ROOT), "merge-base", "--is-ancestor",
                       HERO_AUTHORIZATION_HEAD, "HEAD"], capture_output=True).returncode != 0:
        raise ValueError("authorization preview HEAD must be an ancestor of the candidate")
    if nov16_inventory(record, HERO_MAINTENANCE) != maintenance:
        raise ValueError("publication record must bind independently reviewed maintenance bytes")
    return True


def load_poll_copy_approval(filename, sandbox_url=None):
    """One immutable clipboard script, two existing pages, German's exact consent."""
    if not filename:
        return {}
    path = Path(filename).absolute()
    if (any(p.is_symlink() for p in (path, *path.parents))
            or path.resolve().is_relative_to(ROOT.resolve())):
        raise ValueError("poll-copy approval must be a private non-symlink file outside the repository")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "r", encoding="utf-8") as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600):
            raise ValueError("poll-copy approval must be operator-owned, regular and mode 0600")
        record = json.load(stream, object_pairs_hook=unique_json_fields)
    expected = {
        "version": 1, "purpose": "poll-copy-sandbox", "sandbox_id": "poll-model-release",
        "authorizer_id": "U0CE2G08ZRC",
        "source": {"channel_id": "C0CEMKENSQ1", "message_ts": "1794242873.127109"},
        "script": {"path": POLL_COPY_SCRIPT, "sha256": POLL_COPY_SHA256},
        "pages": POLL_COPY_PAGES, "routes": POLL_COPY_ROUTES,
    }
    if (not isinstance(record, dict) or record != expected or type(record.get("version")) is not int
            or git("branch", "--show-current").strip() != "sandbox/poll-model-release"):
        raise ValueError("poll-copy approval must match the exact schema, German authorization, digest and sandbox branch")
    if sandbox_url:
        url = urlsplit(sandbox_url)
        if (url.scheme != "https" or url.netloc != "forabrighterevanston.org"
                or url.path.rstrip("/") != "/sandbox/poll-model-release" or url.query or url.fragment):
            raise ValueError("poll-copy approval sandbox does not match deployed URL")
    target = ROOT / POLL_COPY_SCRIPT
    if (any(p.is_symlink() for p in (target, *target.parents)) or not target.is_file()
            or target.stat().st_mode & 0o111
            or not git("ls-tree", "HEAD", "--", POLL_COPY_SCRIPT).startswith("100644 ")):
        raise ValueError("poll-copy requires a regular non-executable 100644 committed script; no deletions")
    committed = subprocess.run(["git", "-C", str(ROOT), "show", f"HEAD:{POLL_COPY_SCRIPT}"],
                               check=True, capture_output=True).stdout
    if (hashlib.sha256(committed).hexdigest() != POLL_COPY_SHA256
            or hashlib.sha256(target.read_bytes()).hexdigest() != POLL_COPY_SHA256):
        raise ValueError("poll-copy SHA-256 must match both committed revision and working bytes")
    return record


def scoped_css_problem(text, scope):
    """Conservative CSS subset: scoped selectors, declarations, media/supports only.

    No escape syntax, fetches, imports, global keyframes or executable legacy CSS.
    This is a safety boundary, not a complete CSS parser or visual review.
    """
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    if re.search(r"\\|url\s*\(|@import|expression\s*\(|javascript|behavior\s*:|-moz-binding|<", text, re.I):
        return "CSS contains escapes, external resources or unsafe syntax"
    # Mask strings so quoted braces cannot change the structural parser.
    text = re.sub(r'''"[^"\n]*"|'[^'\n]*' ''', '"value"', text, flags=re.X)

    def scoped_selector(selector):
        selector = selector.strip()
        if not re.match(re.escape(scope) + r"(?=[\s.#:\[>]|$)", selector) or "||" in selector:
            return False
        # Remove attribute/function interiors before finding the first combinator.
        # A sibling of the wrapper escapes scope; siblings of its descendants do not.
        tail = selector[len(scope):]
        previous = None
        while tail != previous:
            previous = tail
            tail = re.sub(r"\([^()]*\)|\[[^\[\]]*\]", "", tail)
        combinator = re.search(r"[\s>+~]", tail)
        return not combinator or not tail[combinator.start():].lstrip().startswith(("+", "~"))

    def rules(source):
        while source.strip():
            opening = source.find("{")
            if opening < 0:
                return False
            head = source[:opening].strip()
            depth, end = 1, opening + 1
            while end < len(source) and depth:
                depth += (source[end] == "{") - (source[end] == "}")
                end += 1
            if depth:
                return False
            body = source[opening + 1:end - 1]
            source = source[end:]
            if head.startswith("@"):
                if not re.fullmatch(r"@(media|supports)\b[^{};]+", head, re.I) or not rules(body):
                    return False
            else:
                if not head or any(not scoped_selector(s) for s in head.split(",")) or "{" in body or "}" in body:
                    return False
        return True

    return None if rules(text) else "every CSS selector must start with the approved page scope; only media/supports nesting is allowed"


def workbook_problem(target):
    """Inspect OOXML without executing formulas, resaving or trusting its extension."""
    try:
        with zipfile.ZipFile(target) as archive:
            entries = archive.infolist()
            names = [entry.filename for entry in entries]
            if len(names) != len(set(names)) or sum(e.file_size for e in entries) > 100 * 1024 * 1024:
                return "duplicate ZIP entries or excessive expanded workbook size"
            for entry in entries:
                name = entry.filename.lower()
                if (not entry.is_dir() and not name.endswith(".rels")
                        and Path(name).suffix not in {".xml", ".png", ".jpg", ".jpeg", ".gif", ".emf", ".wmf"}
                        and not re.fullmatch(r"xl/printersettings/printersettings[0-9]+\.bin", name)):
                    return "unsupported packaged binary or executable file"
                if (name.startswith("/") or ".." in name.split("/") or "\\" in name or entry.flag_bits & 1
                        or re.search(r"vba|macrosheet|dialogsheet|activex|embedding|externallink|customui", name)):
                    return "macros, embedded code/objects, external workbooks or unsafe ZIP entries"
                if name.endswith((".xml", ".rels")):
                    content = archive.read(entry)
                    if b"<!DOCTYPE" in content.upper() or b"<!ENTITY" in content.upper():
                        return "unsafe XML declarations"
                    tree = ET.fromstring(content)
                    for node in tree.iter():
                        if ("macroenabled" in str(node.attrib).lower() or "vbaproject" in str(node.attrib).lower()
                                or node.attrib.get("TargetMode", "").lower() == "external"):
                            return "macro-enabled content or external relationships"
                        if node.tag.rsplit("}", 1)[-1] == "f" and re.search(
                                r"\[|\||\b(?:WEBSERVICE|RTD|CALL|EXEC|REGISTER(?:\.ID)?)\s*\(", node.text or "", re.I):
                            return "external or executable formula"
            if not {"[Content_Types].xml", "xl/workbook.xml", "_rels/.rels"}.issubset(names):
                return "not an OOXML workbook"
            content_types = archive.read("[Content_Types].xml")
            if b"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml" not in content_types:
                return "not a macro-free XLSX workbook"
    except (OSError, zipfile.BadZipFile, ET.ParseError, RuntimeError, ValueError):
        return "invalid or unreadable XLSX archive"
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="origin/main", help="what the sandbox is compared to (default origin/main)")
    ap.add_argument("--url", help="deployed sandbox address, e.g. https://forabrighterevanston.org/sandbox/faq-page/")
    ap.add_argument("--approval-file", help="operator-owned private sandbox-review authorization JSON, outside the repository")
    ap.add_argument("--maintenance-approval-file", help="separate German-only private delegation-maintenance or poll-copy-maintenance authorization JSON")
    ap.add_argument("--poll-copy-approval-file", help="German-only private hash-bound poll-copy-sandbox authorization JSON")
    ap.add_argument("--deletion-approval-file", help="German-only private exact nov16 page-deletion authorization JSON")
    ap.add_argument("--nov16-maintenance-approval-file", help="German-only private exact nov16 checker-maintenance authorization JSON")
    ap.add_argument("--letter-vote-approval-file", help="private exact bilingual letter-copy approval with date, delegation and removal provenance")
    ap.add_argument("--letter-vote-maintenance-approval-file", help="private exact letter-vote checker-maintenance approval JSON")
    ap.add_argument("--hearing-approval-file", help="private exact closure-hearings authorization and maintenance record")
    ap.add_argument("--homepage-hero-approval-file", help="private reviewed homepage hero asset approval JSON")
    ap.add_argument("--homepage-hero-maintenance-approval-file", help="private reviewed homepage hero safety-maintenance approval JSON")
    ap.add_argument("--homepage-hero-maintenance-review-sha256", help="independently reviewed SHA-256 of the exact maintenance record bytes")
    ap.add_argument("--homepage-hero-publication-approval-file", help="separate private publication-safeguards authorization JSON (not a vote)")
    ap.add_argument("--homepage-hero-publication-review-sha256", help="independently attested SHA-256 of exact publication-safeguards record bytes")
    ap.add_argument("--youtube-approval-file", help="original private exact YouTube exception record for the combined hero candidate")
    ap.add_argument("--mailchimp-script-approval-file", help="independently reviewed private preview behavior approval JSON")
    ap.add_argument("--mailchimp-script-maintenance-approval-file", help="separate independently reviewed private preview maintenance approval JSON")
    ap.add_argument("--mailchimp-script-review-sha256", help="out-of-band independently attested SHA-256 of exact behavior record bytes")
    ap.add_argument("--mailchimp-script-maintenance-review-sha256", help="out-of-band independently attested SHA-256 of exact maintenance record bytes")
    ap.add_argument("--json", action="store_true", help="print the report as JSON")
    args = ap.parse_args()

    blocking, warnings, spanish, changes, notes = [], [], [], [], []
    mailchimp_behavior, mailchimp_maintenance = {}, {}
    for filename, purpose, digest in ((args.mailchimp_script_approval_file, "mailchimp-script-preview", args.mailchimp_script_review_sha256),
                                      (args.mailchimp_script_maintenance_approval_file, "mailchimp-script-maintenance", args.mailchimp_script_maintenance_review_sha256)):
        try:
            approved = load_mailchimp_approval(filename, purpose, args.base, args.url, digest)
            if purpose == "mailchimp-script-preview":
                mailchimp_behavior = approved
            else:
                mailchimp_maintenance = approved
        except (OSError, ValueError, TypeError, AttributeError, KeyError, subprocess.CalledProcessError) as error:
            blocking.append(f"Invalid {purpose} approval: {error}")
    if bool(mailchimp_behavior) != bool(mailchimp_maintenance):
        blocking.append("Mailchimp preview requires both independent behavior and maintenance records.")
    if mailchimp_behavior and mailchimp_maintenance:
        notes.append("Mailchimp policy pass is not security approval: independent security and checker review of the exact final revision is required; privacy and possible external CAPTCHA review remain. Not live release approval.")
    else:
        mailchimp_behavior, mailchimp_maintenance = {}, {}
    try:
        hearing = load_hearing_approval(args.hearing_approval_file, args.base, args.url)
    except (OSError, ValueError, TypeError, AttributeError, KeyError, subprocess.CalledProcessError) as error:
        hearing = set()
        blocking.append(f"Invalid hearing approval: {error}")
    if hearing:
        notes.append("Hearing record bound to this candidate and maintenance; normal team review and vote and all other holds remain.")
    try:
        video = load_youtube_approval(args.youtube_approval_file, args.base, args.url)
    except (OSError, ValueError, TypeError, AttributeError, KeyError, subprocess.CalledProcessError) as error:
        video = False
        blocking.append(f"Invalid YouTube approval: {error}")
    hero_assets, hero_maintenance = {}, {}
    for filename, purpose in ((args.homepage_hero_approval_file, "homepage-hero-assets"),
                              (args.homepage_hero_maintenance_approval_file, "homepage-hero-maintenance")):
        try:
            approved = load_homepage_hero_approval(filename, purpose, args.base, args.url,
                                                  args.homepage_hero_maintenance_review_sha256, video)
            if purpose == "homepage-hero-assets":
                hero_assets = approved
            else:
                hero_maintenance = approved
        except (OSError, ValueError, TypeError, AttributeError, KeyError, subprocess.CalledProcessError) as error:
            blocking.append(f"Invalid {purpose} approval: {error}")
    if video and not (hero_assets and hero_maintenance):
        blocking.append("YouTube exception requires both independently reviewed hero approvals for this exact HEAD.")
    hero_publication = False
    try:
        hero_publication = load_hero_publication_safeguards(
            args.homepage_hero_publication_approval_file, args.homepage_hero_publication_review_sha256,
            args.base, hero_assets, hero_maintenance)
    except (OSError, ValueError, TypeError, AttributeError, KeyError, subprocess.CalledProcessError) as error:
        blocking.append(f"Invalid homepage-hero publication safeguards approval: {error}")
    if hero_publication:
        notes.append("Publication safeguards reviewed; normal team review and vote, verified deployment, photo permission and all other holds remain. No code action is a vote.")
    elif hero_assets or hero_maintenance:
        notes.append("Reviewed preview only; vote and publication are held until a separately authorized and reviewed publication procedure exists; other holds remain.")
    letter_copy, letter_maintenance = {}, {}
    for filename, purpose in ((args.letter_vote_approval_file, "letter-vote-copy"),
                              (args.letter_vote_maintenance_approval_file, "letter-vote-maintenance")):
        try:
            approved = load_letter_vote_approval(filename, purpose, args.base, args.url)
            if purpose == "letter-vote-copy":
                letter_copy = approved
            else:
                letter_maintenance = approved
            if approved:
                notes.append(f"Bound {purpose} approval; preview only, normal team review and vote remain.")
        except (OSError, ValueError, TypeError, AttributeError, KeyError, subprocess.CalledProcessError) as error:
            blocking.append(f"Invalid {purpose} approval: {error}")
    try:
        approved_deletions = load_nov16_deletion_approval(args.deletion_approval_file, args.base, args.url)
    except (OSError, ValueError, TypeError, AttributeError, KeyError, subprocess.CalledProcessError) as error:
        approved_deletions = set()
        blocking.append(f"Invalid page-deletion approval: {error}")
    if approved_deletions:
        notes.append("German authorized only these four sandbox page deletions; team review/vote and other holds remain.")
    try:
        nov16_maintenance = load_nov16_maintenance_approval(args.nov16_maintenance_approval_file, args.base, args.url)
    except (OSError, ValueError, TypeError, AttributeError, KeyError, subprocess.CalledProcessError) as error:
        nov16_maintenance = {}
        blocking.append(f"Invalid nov16 maintenance approval: {error}")
    if nov16_maintenance:
        notes.append("German-only nov16 fixed-inventory checker maintenance approval; no publication authorization.")
    try:
        poll_copy_approval = load_poll_copy_approval(args.poll_copy_approval_file, args.url)
        if poll_copy_approval:
            notes.append("German-only poll-copy-sandbox approval loaded for the immutable script and two exact page loaders; no live publication authorization. Team review/vote and all other holds remain.")
    except (OSError, ValueError, TypeError, AttributeError, KeyError, subprocess.CalledProcessError) as error:
        poll_copy_approval = {}
        blocking.append(f"Invalid poll-copy approval: {error}")
    try:
        approved_maintenance = load_maintenance_approval(args.maintenance_approval_file, args.url)
    except (OSError, ValueError, TypeError, AttributeError, KeyError, subprocess.CalledProcessError) as error:
        approved_maintenance = {}
        blocking.append(f"Invalid maintenance approval: {error}")
    if approved_maintenance:
        notes.append("German-only fixed-inventory maintenance approval loaded for six exact files in this sandbox only; no live publication authorization. Team review/vote and copy/resource holds remain.")
    try:
        approval = load_scoped_approval(args.approval_file, args.url)
    except (OSError, ValueError, TypeError, AttributeError, KeyError) as error:
        approval = {"css": [], "workbooks": []}
        blocking.append(f"Invalid scoped approval: {error}")
    approved_css = {item["path"]: item for item in approval["css"]}
    approved_workbooks = {item["path"]: item for item in approval["workbooks"]}
    if args.approval_file and (approved_css or approved_workbooks):
        notes.append("Scoped sandbox-review approval loaded; no live publication authorization. Team review/vote and all other holds remain.")

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

        if path in mailchimp_behavior:
            changes.append(f"Reviewed Mailchimp preview {verb}: {path}")
            if path == "_includes/updates-dialog.html":
                warnings.append(f"{path}: check all affected English and Spanish rendered pages in the sandbox; a template is not a standalone route.")
            continue
        if path in mailchimp_maintenance:
            changes.append(f"Separately reviewed Mailchimp maintenance {verb}: {path}")
            continue
        if path in hearing:
            changes.append(f"Reviewed hearing authorization {verb}: {path}")
            continue
        if path in letter_copy:
            changes.append(f"Authorized bilingual letter text {verb}: {path}")
            continue
        if path in hero_assets:
            if (path == HERO_SCRIPT and status != "A") or (path == HERO_CSS and status != "M"):
                blocking.append(f"{path}: hero approval requires the exact new script and modified stylesheet, no deletion or mode changes.")
            else:
                changes.append(f"Reviewed homepage hero asset {verb}: {path}")
            continue
        if poll_copy_approval and path == POLL_COPY_SCRIPT:
            base_mode = git("ls-tree", args.base, "--", path)
            if status not in {"A", "M"} or (base_mode and not base_mode.startswith("100644 ")):
                blocking.append(f"{path}: poll-copy authorizes no deletion, type or mode changes.")
            else:
                changes.append(f"German-authorized poll-copy script {verb}: {path}")
            continue
        if path in approved_maintenance or path in nov16_maintenance or path in letter_maintenance or path in hero_maintenance:
            if status not in {"A", "M"}:
                blocking.append(f"{path}: maintenance authorizes additions/updates only, never deletion or type changes.")
            else:
                authorizer = "Delegate" if path in letter_maintenance or path in hero_maintenance else "German"
                changes.append(f"{authorizer}-authorized fixed-inventory maintenance {verb}: {path}")
            continue
        if path in approved_css or path in approved_workbooks:
            target = ROOT / path
            if (status not in {"A", "M"} or any(p.is_symlink() for p in (target, *target.parents))
                    or not target.is_file() or not git("ls-tree", "HEAD", "--", path).startswith("100644 ")):
                blocking.append(f"{path}: scoped assets must be regular, non-executable files; deletion is not authorized.")
                continue
            if git("diff", "HEAD", "--", path):
                blocking.append(f"{path}: scoped asset differs from the committed revision; commit before validation.")
                continue
            if target.stat().st_size > MEDIA_MAX_BYTES:
                blocking.append(f"{path}: scoped asset exceeds the 5 MB limit.")
                continue
            if path in approved_css:
                try:
                    problem = scoped_css_problem(target.read_text(encoding="utf-8"), approved_css[path]["scope"])
                except UnicodeError:
                    problem = "CSS must be UTF-8 text"
                warnings.append(f"{path}: verify the stylesheet is loaded only on its approved routes and its scope wrapper exists only there; review both languages on desktop/phone.")
            else:
                problem = workbook_problem(target)
                if hashlib.sha256(target.read_bytes()).hexdigest() != approved_workbooks[path]["sha256"]:
                    problem = "workbook SHA-256 does not match the unchanged supplied file"
            if problem:
                blocking.append(f"{path}: {problem}.")
            changes.append(f"Scoped sandbox-review asset {verb}: {path}")
            continue
        if path == "data/news.json":
            blocking.append("The news list (data/news.json) was changed. News is managed only in #news; this change must be removed.")
            continue
        if path.startswith(TEMPLATE_DIRS) and ext in TEMPLATE_EXT:
            if status == "D":
                blocking.append(f"{path} was deleted. Templates may be added or updated, not deleted.")
                continue
            if (ROOT / path).is_symlink() or git("ls-tree", "HEAD", "--", path).startswith("120000 "):
                blocking.append(f"{path}: template symlinks aren't allowed.")
                continue
            text = (ROOT / path).read_text(encoding="utf-8")
            if template_hazards(text) - template_hazards(git_show(args.base, path) or ""):
                blocking.append(f"{path}: adds or modifies unsafe HTML or executable code, which isn't allowed in templates.")
            changes.append(f"Template {verb}: {path}")
            warnings.append(f"{path}: check all affected English and Spanish rendered pages in the sandbox; a template is not a standalone route.")
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
            target = ROOT / path
            if target.is_symlink() or not target.is_file():
                blocking.append(f"{path}: media must be a regular file, not a symlink or missing file.")
                continue
            size = target.stat().st_size
            if size > MEDIA_MAX_BYTES:
                blocking.append(f"{path} is {size/1048576:.1f} MB; the limit is 5 MB. Resize or compress it.")
            elif size > MEDIA_WARN_BYTES and ext in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
                warnings.append(f"{path} is {size//1024} KB; images over 500 KB slow the site down on phones. Resize it to about 1600 px wide.")
            changes.append(f"File {verb}: {path} ({size//1024} KB)")
            continue

        if ext in PAGE_EXT and not path.startswith("_"):
            if status == "D":
                if path in approved_deletions:
                    changes.append(f"German-authorized page deletion: {path}")
                    continue
                blocking.append(f"The page {path} was deleted. Deleting published pages breaks existing links; ask German or Kerstin for scoped authorization and reviewed enforcement.")
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
    added_files = {path for status, path in entries if status == "A"}
    generic_images = generic_share_images(args.base) if any(st == "A" for *_, st in changed_pages) else set()
    for path, fm, body, status in changed_pages:
        label = f"{path}"
        if fm is None or not fm:
            blocking.append(f"{label}: missing the page settings block (front matter between --- lines).")
            continue
        layout = fm.get("layout")
        layout_paths = []
        if isinstance(layout, str) and re.fullmatch(r"[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*", layout):
            layout_paths = [f"_layouts/{layout}{ext}" for ext in sorted(TEMPLATE_EXT)
                            if f"_layouts/{layout}{ext}" in all_pages]
        if not layout_paths:
            blocking.append(f"{label}: layout {layout!r} must name an existing HTML, Liquid or Markdown layout (no traversal or file extensions).")
        for layout_path in layout_paths:
            target = ROOT / layout_path
            if target.is_symlink() or git("ls-tree", "HEAD", "--", layout_path).startswith("120000 "):
                blocking.append(f"{label}: layout {layout!r} is a symlink, which isn't allowed.")
            elif template_hazards(target.read_text(encoding="utf-8")) - template_hazards(git_show(args.base, layout_path) or ""):
                blocking.append(f"{label}: layout {layout!r} adds or modifies unsafe HTML or executable code.")
        if fm.get("lang") not in ("en", "es"):
            blocking.append(f"{label}: lang must be \"en\" or \"es\" (found {fm.get('lang')!r}).")
        for k in ("title", "description"):
            if not isinstance(fm.get(k), str) or not fm[k].strip():
                blocking.append(f"{label}: {k} must be a nonempty string.")
        allowed_fm = {"layout", "lang", "title", "description", "alt_url", "share_title", "share_description", "share_image", "nav", "css", "scripts", "body_class", "permalink", "is_home"}
        extra = set(fm) - allowed_fm
        if extra:
            warnings.append(f"{label}: unusual settings {sorted(extra)}.")
        if status == "A":
            problem = share_image_problem(fm.get("share_image"), added_files, generic_images)
            if problem:
                blocking.append(f"{label}: share_image {problem}.")
            warnings.append(f"{label}: include the sharing card in review; check page-specific visual relevance, localized English/Spanish title and description, and localized image text. A language-neutral image may be shared; 1200×630 is recommended. This check cannot verify visual meaning or platform caches.")
            for k in ("css", "scripts", "nav", "is_home"):
                if k in fm:
                    blocking.append(f"{label}: new pages can't set {k!r}; that changes how the site works.")
        base_text = git_show(args.base, path)
        if base_text is not None:
            base_fm = parse_front_matter(split_front_matter(base_text)[0])
            for k in ("css", "scripts", "nav", "is_home", "permalink", "lang"):
                if base_fm.get(k) != fm.get(k):
                    if (k == "scripts" and hero_assets and path in HERO_PAGES
                            and page_url(path, fm) == HERO_ROUTES[HERO_PAGES.index(path)]
                            and isinstance(base_fm.get(k), list)
                            and fm.get(k) == base_fm[k] + ["hero-slideshow.js"]):
                        continue
                    if (k == "scripts" and poll_copy_approval and path in POLL_COPY_PAGES
                            and base_fm.get(k) in (None, []) and fm.get(k) == ["poll-copy.js"]
                            and page_url(path, fm) == POLL_COPY_ROUTES[POLL_COPY_PAGES.index(path)]):
                        continue
                    blocking.append(f"{label}: the {k!r} setting was changed; that's structural.")

        # Only flag what this update introduced (existing pages may use includes by design)
        base_body = split_front_matter(base_text)[1] if base_text is not None else ""
        for rx, what in UNSAFE:
            if len(rx.findall(body)) > len(rx.findall(base_body)):
                if (video and hero_assets and hero_maintenance and path in VIDEO_FILES
                        and what == "an embedded frame or object"):
                    continue  # exact pinned page bytes contain only the reviewed YouTube player
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
        # Load all changed pages at once, then check every unique same-site
        # link at once; messages are reported in the same order as before.
        page_urls = [urljoin(base_url, page_url(path, fm).lstrip("/")) for path, fm, body, st in changed_pages]
        with ThreadPoolExecutor(max_workers=LINK_WORKERS) as pool:
            fetched = list(pool.map(fetch, page_urls))
        checked = set()
        to_check = []  # (page url, tag, link, full url) in report order
        for (path, fm, body, st), url, (code, html) in zip(changed_pages, page_urls, fetched):
            if code != 200:
                blocking.append(f"{url} doesn't load (HTTP {code}).")
                continue
            parser = LinkParser()
            parser.feed(html)
            if video and hero_assets and hero_maintenance and path in HERO_PAGES:
                actual = DiscoveryParser()
                actual.feed(html)
                try:
                    expected = expected_discovery(fm.get("lang"), base_url)
                except (OSError, ValueError):
                    expected = []
                if len(expected) != 1 or actual.sections != expected or actual.depth or actual.inert:
                    blocking.append(f"{url}: deployed video discovery content or sandbox-relative localized link differs from the approved rendering.")
            if video and hero_assets and hero_maintenance and path in VIDEO_FILES:
                approved = LinkParser()
                approved.feed(body)
                existing_form_frame = sorted([("name", "gf_hidden"), ("title", "Form submission"), ("hidden", None)], key=repr)
                actual_frames = [sorted(frame, key=repr) for frame in parser.iframes]
                expected_player = sorted(approved.iframes[0], key=repr) if len(approved.iframes) == 1 else None
                if (expected_player is None or actual_frames.count(expected_player) != 1
                        or actual_frames.count(existing_form_frame) > 1
                        or any(frame not in (expected_player, existing_form_frame) for frame in actual_frames)):
                    blocking.append(f"{url}: deployed video player must be the single exact approved iframe and attributes.")
                rendered_body = re.sub(r"{{ '(.*?)' \| relative_url }}",
                                       lambda m: urlsplit(base_url).path + m.group(1).lstrip("/"), body)
                for marker in (("class", "page-hero"), ("aria-label", "Video")):
                    actual_section, expected_section = DiscoveryParser(marker), DiscoveryParser(marker)
                    actual_section.feed(html)
                    expected_section.feed(rendered_body)
                    if (len(expected_section.sections) != 1 or actual_section.depth or actual_section.inert
                            or actual_section.sections != expected_section.sections):
                        blocking.append(f"{url}: deployed video content differs from the approved rendering.")
            if st == "A":
                sharing_description = fm.get("share_description") or fm.get("description", "")
                expected = {"og:title": fm.get("share_title") or fm.get("title"),
                            "og:description": re.sub(r"<[^>]*>", "", sharing_description)
                            if isinstance(sharing_description, str) else None,
                            "twitter:card": "summary_large_image"}
                image = fm.get("share_image")
                expected["og:image"] = urljoin(base_url, image.lstrip("/")) if isinstance(image, str) else None
                for key, value in expected.items():
                    if not value or parser.metadata.get(key) != [value]:
                        blocking.append(f"{url}: {key} is missing, duplicated or does not match the page sharing settings (expected {value!r}).")
                if not share_image_problem(image, added_files, generic_images):
                    image_url = expected["og:image"]
                    image_status, mime, has_content = fetch_sharing_image(image_url)
                    if image_status != 200 or not mime.startswith("image/") or not has_content:
                        blocking.append(f"{url}: sharing image {image_url} must load with image MIME and nonempty content (HTTP {image_status}, MIME {mime!r}).")
                    if (video and hero_assets and hero_maintenance and path in VIDEO_FILES
                            and (image.lstrip("/") not in VIDEO_FILES
                                 or not fetch_approved_video_card(image_url, VIDEO_FILES[image.lstrip("/")]))):
                        blocking.append(f"{url}: sharing image {image_url} bytes could not be verified against the approved video card.")
            for tag, link in parser.links:
                full = urljoin(url, link)
                parts = urlsplit(full)
                if parts.scheme not in ("http", "https") or full in checked:
                    continue
                checked.add(full)
                if parts.netloc != urlsplit(base_url).netloc:
                    continue  # outside links aren't checked
                to_check.append((url, tag, link, full))
        targets = sorted({full.split("#")[0] for _, _, _, full in to_check})
        with ThreadPoolExecutor(max_workers=LINK_WORKERS) as pool:
            statuses = dict(zip(targets, pool.map(link_status, targets)))
        for url, tag, link, full in to_check:
            c = statuses[full.split("#")[0]]
            if c >= 400 or c == 0:
                blocking.append(f"{url}: broken {'image' if tag == 'img' else 'link'} → {link} (HTTP {c}).")
            elif "/sandbox/" in base_url and "/sandbox/" not in urlsplit(full).path and tag in ("a", "img"):
                warnings.append(f"{url}: {tag} {link} points to the live site instead of the sandbox.")

    report = {"blocking": blocking, "warnings": warnings, "spanish": spanish, "changes": changes, "notes": notes}
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for title, items in (("BLOCKING", blocking), ("WARNINGS", warnings), ("SPANISH", spanish), ("CHANGES", changes), ("NOTES", notes)):
            print(f"{title} ({len(items)})")
            for i in items:
                print(f"  - {i}")
        if blocking:
            result = "NOT READY FOR A VOTE"
        elif (hero_assets or hero_maintenance) and not hero_publication:
            result = "OK FOR PREVIEW ONLY (vote/publication held)"
        else:
            result = "OK TO VOTE (review warnings)"
        print("RESULT:", result)
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
