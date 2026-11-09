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

    def handle_starttag(self, tag, attrs):
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


def fetch(url, method="GET"):
    req = urllib.request.Request(url, method=method, headers={"User-Agent": "fabian-sandbox-check"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, (r.read().decode("utf-8", "replace") if method == "GET" else "")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:  # network errors
        return 0, str(e)


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


def unique_json_fields(pairs):
    record = {}
    for key, value in pairs:
        if key in record:
            raise ValueError("duplicate approval field: " + key)
        record[key] = value
    return record


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
    ap.add_argument("--json", action="store_true", help="print the report as JSON")
    args = ap.parse_args()

    blocking, warnings, spanish, changes, notes = [], [], [], [], []
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

        if poll_copy_approval and path == POLL_COPY_SCRIPT:
            base_mode = git("ls-tree", args.base, "--", path)
            if status not in {"A", "M"} or (base_mode and not base_mode.startswith("100644 ")):
                blocking.append(f"{path}: poll-copy authorizes no deletion, type or mode changes.")
            else:
                changes.append(f"German-authorized poll-copy script {verb}: {path}")
            continue
        if path in approved_maintenance:
            if status not in {"A", "M"}:
                blocking.append(f"{path}: maintenance authorizes additions/updates only, never deletion or type changes.")
            else:
                changes.append(f"German-authorized fixed-inventory maintenance {verb}: {path}")
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
                    if (k == "scripts" and poll_copy_approval and path in POLL_COPY_PAGES
                            and base_fm.get(k) in (None, []) and fm.get(k) == ["poll-copy.js"]
                            and page_url(path, fm) == POLL_COPY_ROUTES[POLL_COPY_PAGES.index(path)]):
                        continue
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
