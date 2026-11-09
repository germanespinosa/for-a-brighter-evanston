#!/usr/bin/env python3
"""Help build website pages from mockups: extract their text, find missing
information, and check the built page copies the text verbatim.

Run from the repository root:

  python3 scripts/mockup_check.py extract MOCKUP [--out text.txt]
      Print the mockup's visible text, one numbered segment per line, plus
      its links and images (HTML). MOCKUP may be .html/.htm, .pdf, .txt/.md,
      or an image (.png/.jpg/.jpeg/.webp). Images are read with OCR, which
      makes mistakes: treat that output as a draft, correct it word by word
      against the image, save it as a .txt file and use that file instead.

  python3 scripts/mockup_check.py placeholders MOCKUP
      List text that looks like missing information ("[day of the event]",
      "TBD", "Lorem ipsum", "XX:XX", links that go nowhere, placeholder
      images...). Exit code 1 if anything was found.

  python3 scripts/mockup_check.py compare MOCKUP PAGE [--fills fills.json]
      PAGE is the built page: a URL (e.g. the sandbox page) or a local .html
      file. Only the page's <main> content is compared, not the site header,
      menu or footer. Every mockup text segment must appear on the page
      exactly (only spacing may differ). Reports:
        CHANGED      text that is missing or worded differently
        MINOR        differs only in quotes, dashes, capitalization or spacing
                     around punctuation (still not verbatim: fix or confirm)
        PLACEHOLDER  missing-information text still on the page
        FILLED       a placeholder segment replaced using --fills
        ADDED        page text that isn't in the mockup (check it's wanted)
      --fills is a JSON object mapping each placeholder exactly as written in
      the mockup to the answer the requester gave, e.g.
        {"[day of the event]": "Saturday, November 14"}
      Segments are then compared with those answers substituted in.
      Exit code 1 if anything is CHANGED, MINOR or PLACEHOLDER.

Uses only the Python standard library, plus pdftotext (poppler) or pypdf for
PDFs and tesseract for images when available.
"""
import argparse
import difflib
import json
import re
import shutil
import subprocess
import sys
import unicodedata
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

BLOCK_TAGS = {
    "address", "article", "aside", "blockquote", "br", "button", "caption", "dd", "details",
    "div", "dl", "dt", "figcaption", "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5",
    "h6", "header", "hr", "label", "legend", "li", "main", "nav", "ol", "option", "p", "pre",
    "section", "summary", "table", "td", "text", "th", "tr", "ul", "tspan",
}
SKIP_TAGS = {"script", "style", "noscript", "template", "head", "title"}
CHROME_TAGS = {"header", "nav", "footer"}   # a mockup's own site header, menu and footer
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".tif", ".tiff"}

PLACEHOLDER_PATTERNS = [
    (r"\[[^\[\]\n]{1,120}\]", "text in [square brackets]"),
    (r"\{\{[^{}\n]{0,80}\}\}|\{[A-Za-z_][^{}\n]{0,60}\}", "text in {curly braces}"),
    (r"<<[^<>\n]{1,80}>>|<[A-Z][A-Z _-]{2,60}>", "text in <angle brackets>"),
    (r"\b(?:TBD|TBA|TBC|TK)\b", "TBD / TBA / TBC"),
    (r"(?i)\bto be (?:determined|confirmed|announced)\b|\bpor (?:confirmar|definir|determinar|anunciar)\b", "to be determined"),
    (r"(?i)\blorem ipsum(?: dolor sit amet)?\b|(?<!ipsum )\bdolor sit amet\b", "Lorem ipsum filler"),
    (r"(?i)\bplaceholder\b|\bmarcador de posición\b", "the word placeholder"),
    (r"(?i)\b(?:insert|add|put|paste|enter|agregar|insertar|poner)\b[^.\n]{0,40}\bhere\b|\baquí va\b", "an 'insert … here' instruction"),
    (r"(?i)\b(?:date|time|day|location|address|link|url|name|title|text|phone|email|image|photo|logo|fecha|hora|lugar|enlace|nombre)\s+(?:here|goes here|aquí)\b", "a '… here' marker"),
    (r"\b[Xx]{2,}\b|\bX+:X+\b|\bXX?/XX?\b", "XX markers"),
    (r"\b(?:MM/DD(?:/YY(?:YY)?)?|DD/MM(?:/YY(?:YY)?)?|HH:MM|YYYY)\b", "a date/time format instead of a value"),
    (r"\b00[/.:-]00(?:[/.:-]\d{2,4})?\b|\b0?0:00 ?[AaPp]\.?[Mm]\.?\b", "a zeroed date or time"),
    (r"\?{2,}", "question marks (??)"),
    (r"(?i)\b(?:john|jane) (?:doe|smith)\b|\bexample\.(?:com|org)\b|\b555[- .]\d{4}\b|\(555\)", "sample name, email or phone"),
    (r"(?i)\bcoming soon\b|\bpróximamente\b", "'coming soon'"),
]
PLACEHOLDER_IMAGE_HOSTS = re.compile(r"(?i)placehold|placeholder|dummyimage|picsum|lorempixel|via\.placeholder")


class TextExtractor(HTMLParser):
    """Visible text segments, links and images from HTML. With main_only,
    only text inside <main> is kept (if the page has a <main>)."""

    def __init__(self, main_only=False):
        super().__init__(convert_charrefs=True)
        self.main_only = main_only
        self.skip = 0
        self.in_main = 0
        self.saw_main = False
        self.buf = []
        self.segments = []
        self.all_segments = []
        self.chrome = 0
        self.chrome_idx = set()   # indexes in segments that were inside header/nav/footer
        self.links = []
        self.images = []
        self._link = None

    def _keep(self):
        return not self.main_only or self.in_main > 0

    def flush(self):
        text = normalize_space("".join(self.buf))
        self.buf = []
        if text and re.search(r"\w", text):
            self.all_segments.append(text)
            if self._keep():
                if self.chrome:
                    self.chrome_idx.add(len(self.segments))
                self.segments.append(text)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in SKIP_TAGS:
            self.skip += 1
            return
        if tag in BLOCK_TAGS:
            self.flush()
        if tag == "main":
            self.flush()
            self.in_main += 1
            self.saw_main = True
        if tag in CHROME_TAGS and not self.skip:
            self.flush()
            self.chrome += 1
        if self.skip:
            return
        if tag == "a":
            self._link = {"href": a.get("href"), "text": []}
        if tag == "img":
            self.images.append({"src": a.get("src") or "", "alt": a.get("alt")})
        if tag == "input" and a.get("type") in ("submit", "button") and a.get("value"):
            self.flush()
            self.buf.append(a["value"])
            self.flush()

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS:
            self.skip = max(0, self.skip - 1)
            return
        if tag == "a" and self._link is not None:
            self._link["text"] = normalize_space("".join(self._link["text"]))
            self.links.append(self._link)
            self._link = None
        if tag in BLOCK_TAGS:
            self.flush()
        if tag == "main":
            self.flush()
            self.in_main = max(0, self.in_main - 1)
        if tag in CHROME_TAGS:
            self.flush()
            self.chrome = max(0, self.chrome - 1)

    def handle_data(self, data):
        if self.skip:
            return
        self.buf.append(data)
        if self._link is not None:
            self._link["text"].append(data)

    def close(self):
        super().close()
        self.flush()
        if self.main_only and not self.saw_main:
            self.segments = list(self.all_segments)


def normalize_space(text):
    text = unicodedata.normalize("NFC", text.replace(" ", " ").replace("​", ""))
    return re.sub(r"\s+", " ", text).strip()


def loose(text):
    """For MINOR comparisons: same words, ignoring quote/dash style, case and
    spacing around punctuation."""
    t = normalize_space(text)
    t = re.sub(r"[‘’‚‛′`´]", "'", t)
    t = re.sub(r"[“”„‟″«»]", '"', t)
    t = re.sub(r"[‐‑‒–—―−]", "-", t)
    t = t.replace("…", "...")
    t = re.sub(r"\s*([,.;:!?)\]])", r"\1", t)
    t = re.sub(r"([(\[])\s*", r"\1", t)
    return t.casefold()


def read_html(path_or_text, main_only=False, is_text=False):
    p = TextExtractor(main_only=main_only)
    p.feed(path_or_text if is_text else Path(path_or_text).read_text(encoding="utf-8", errors="replace"))
    p.close()
    return p


def pdf_text(path):
    if shutil.which("pdftotext"):
        out = subprocess.run(["pdftotext", "-nopgbrk", "-enc", "UTF-8", str(path), "-"],
                             capture_output=True, text=True, check=True).stdout
    else:
        try:
            from pypdf import PdfReader
        except ImportError:
            sys.exit("Can't read PDFs here: install poppler-utils (pdftotext) or pypdf.")
        out = "\n\n".join((page.extract_text() or "") for page in PdfReader(str(path)).pages)
    return out


def paragraphs(text):
    """Split plain text into segments: blank lines separate paragraphs; single
    line breaks inside a paragraph are joined (PDF line wrapping)."""
    segs = []
    for block in re.split(r"\n\s*\n", text.replace("\r", "")):
        lines = [normalize_space(l) for l in block.split("\n")]
        lines = [l for l in lines if l]
        if not lines:
            continue
        # Lines that look like separate items (bullets, short headings) stay separate
        cur = ""
        for line in lines:
            item = re.match(r"^([•▪●◦\-*–]|\d+[.)])\s+", line)
            if not cur:
                cur = line
            elif item or (len(cur) < 60 and not re.search(r"[,;:a-z]$", cur)):
                segs.append(cur)
                cur = line
            else:
                cur = cur[:-1] + line if cur.endswith("-") and re.match(r"[a-z]", line) else cur + " " + line
        if cur:
            segs.append(cur)
    return [s for s in segs if re.search(r"\w", s)]


def image_text(path):
    if not shutil.which("tesseract"):
        sys.exit("Can't read text from images here (tesseract isn't installed). Read the image yourself, "
                 "type its text exactly into a .txt file (one paragraph per block, blank line between) and use that file.")
    out = subprocess.run(["tesseract", str(path), "-", "-l", "eng+spa"], capture_output=True, text=True)
    if out.returncode != 0:
        out = subprocess.run(["tesseract", str(path), "-"], capture_output=True, text=True, check=True)
    return out.stdout


def load_mockup(path):
    path = Path(path)
    ext = path.suffix.lower()
    info = {"kind": ext.lstrip("."), "segments": [], "links": [], "images": [], "draft": False, "chrome": set()}
    if ext in (".html", ".htm"):
        p = read_html(path)
        info.update(segments=p.segments, links=p.links, images=p.images, chrome=p.chrome_idx)
    elif ext == ".pdf":
        info["segments"] = paragraphs(pdf_text(path))
    elif ext in (".txt", ".md", ".markdown"):
        info["segments"] = paragraphs(path.read_text(encoding="utf-8", errors="replace"))
    elif ext in IMAGE_EXT:
        info["segments"] = paragraphs(image_text(path))
        info["draft"] = True
    else:
        sys.exit(f"Unsupported mockup type {ext or '(none)'}: use HTML, PDF, TXT/MD or an image.")
    return info


def find_placeholders(info):
    found = []
    for i, seg in enumerate(info["segments"], 1):
        for rx, what in PLACEHOLDER_PATTERNS:
            for m in re.finditer(rx, seg):
                found.append({"segment": i, "text": m.group(0), "kind": what, "context": seg})
    for link in info.get("links", []):
        href = (link.get("href") or "").strip()
        if not href or href == "#" or href.lower().startswith("javascript:") or PLACEHOLDER_IMAGE_HOSTS.search(href):
            found.append({"segment": None, "text": link.get("text") or "(link with no text)",
                          "kind": "link or button with no real destination", "context": f"href={href!r}"})
    for img in info.get("images", []):
        src = img.get("src") or ""
        if not src or PLACEHOLDER_IMAGE_HOSTS.search(src):
            found.append({"segment": None, "text": img.get("alt") or "(image)",
                          "kind": "placeholder image", "context": f"src={src!r}"})
    # One entry per placeholder occurrence in a segment (patterns can overlap)
    seen, unique = set(), []
    for f in found:
        key = (f["segment"], f["text"], f["context"])
        if key not in seen:
            seen.add(key)
            unique.append(f)
    return unique


def page_segments(page):
    if re.match(r"https?://", page):
        req = urllib.request.Request(page, headers={"User-Agent": "fabian-mockup-check"})
        with urllib.request.urlopen(req, timeout=30) as r:
            html = r.read().decode("utf-8", "replace")
        return read_html(html, main_only=True, is_text=True).segments
    return read_html(page, main_only=True).segments


def cmd_extract(args):
    info = load_mockup(args.mockup)
    lines = []
    if info["draft"]:
        lines.append("# OCR DRAFT: compare every word with the image and correct it before using this text.")
    for i, seg in enumerate(info["segments"], 1):
        mark = "  (mockup header/menu/footer)" if (i - 1) in info["chrome"] else ""
        lines.append(f"{i:>3}. {seg}{mark}")
    if info["links"]:
        lines.append("\n# Links and buttons")
        for l in info["links"]:
            lines.append(f"  - {l.get('text') or '(no text)'} → {l.get('href') or '(no destination)'}")
    if info["images"]:
        lines.append("\n# Images")
        for im in info["images"]:
            lines.append(f"  - {im.get('src') or '(no source)'}  alt={im.get('alt')!r}")
    out = "\n".join(lines)
    if args.out:
        Path(args.out).write_text("\n\n".join(info["segments"]) + "\n", encoding="utf-8")
        print(f"Saved {len(info['segments'])} text segments to {args.out} (one paragraph per block).")
    print(out)
    return 0


def cmd_placeholders(args):
    info = load_mockup(args.mockup)
    found = find_placeholders(info)
    if info["draft"]:
        print("# OCR DRAFT: the image text may be misread; also look at the image yourself.")
    if not found:
        print("No missing-information markers found. Still read the whole mockup: missing details "
              "(an event with no time or place, a button with no destination) aren't always marked.")
        return 0
    print(f"MISSING INFORMATION ({len(found)})")
    for f in found:
        where = f"segment {f['segment']}" if f["segment"] else "link/image"
        print(f"  - {f['text']!r} ({f['kind']}, {where}): {f['context']}")
    return 1


def best_match(seg, page_text):
    """Closest stretch of page text to a missing segment, for the report."""
    n = len(seg)
    if not page_text or n == 0:
        return ""
    if n < 8:
        return ""
    best, best_r = "", 0.0
    step = max(1, n // 6)
    for start in range(0, max(1, len(page_text) - n // 2), step):
        cand = page_text[start:start + n + n // 5]
        r = difflib.SequenceMatcher(None, seg.casefold(), cand.casefold()).ratio()
        if r > best_r:
            best_r, best = r, cand
    return best.strip() if best_r >= 0.6 else ""


def sentences(seg):
    """Compare long segments sentence by sentence, for precise reports."""
    parts = re.split(r"(?<=[.!?])\s+(?=[\"“¿¡(]?[A-ZÁÉÍÓÚÑ0-9])", seg)
    return [p for p in parts if re.search(r"\w", p)]


def cmd_compare(args):
    info = load_mockup(args.mockup)
    fills = json.loads(Path(args.fills).read_text(encoding="utf-8")) if args.fills else {}
    page = page_segments(args.page)
    page_text = normalize_space(" ".join(page))
    page_loose = loose(page_text)
    placeholders = find_placeholders(info)
    ph_texts = {p["text"] for p in placeholders if p["segment"]}

    results = {"OK": [], "FILLED": [], "MINOR": [], "CHANGED": [], "PLACEHOLDER": [], "ADDED": [], "CHROME": []}
    for i, seg in enumerate(info["segments"], 1):
        if (i - 1) in info["chrome"]:
            if normalize_space(seg) not in page_text:
                results["CHROME"].append((i, seg, ""))
            continue
        for unit in sentences(seg):
            expected = unit
            filled = False
            for ph, answer in fills.items():
                if ph in expected:
                    expected = expected.replace(ph, answer)
                    filled = True
            unfilled = sorted(ph for ph in ph_texts if ph in expected)
            exp = normalize_space(expected)
            if exp in page_text:
                if unfilled:
                    results["PLACEHOLDER"].append((i, unit, "still on the page: " + ", ".join(unfilled)))
                else:
                    results["FILLED" if filled else "OK"].append((i, unit, ""))
            elif loose(exp) in page_loose:
                results["MINOR"].append((i, unit, "differs only in quotes, dashes, capitalization or spacing"))
            else:
                notes = []
                if unfilled:
                    notes.append("placeholder not filled: ask the requester, then pass the answer with --fills")
                match = best_match(exp, page_text)
                notes.append(f"closest on page: {match!r}" if match else "not found on the page")
                results["CHANGED"].append((i, unit, "; ".join(notes)))

    mockup_loose = loose(" \n ".join(info["segments"] + [s.replace(k, v) for s in info["segments"] for k, v in fills.items() if k in s]))
    for seg in page:
        if loose(seg) not in mockup_loose:
            results["ADDED"].append((None, seg, ""))

    if info["draft"]:
        print("# OCR DRAFT: mockup text came from OCR; confirm differences against the image before acting.")
    total = len(info["segments"])
    print(f"Mockup paragraphs: {total} · sentences verbatim: {len(results['OK'])} · filled: {len(results['FILLED'])} · "
          f"minor: {len(results['MINOR'])} · changed: {len(results['CHANGED'])} · placeholders left: {len(results['PLACEHOLDER'])}")
    labels = {"CHROME": "MOCKUP HEADER/MENU/FOOTER (not compared: the site keeps its own; ask if these were meant to change)"}
    for key in ("CHANGED", "PLACEHOLDER", "MINOR", "FILLED", "ADDED", "CHROME"):
        items = results[key]
        if not items:
            continue
        print(f"\n{labels.get(key, key)} ({len(items)})")
        for i, seg, note in items:
            label = f"#{i} " if i else ""
            print(f"  - {label}{seg!r}" + (f"\n      {note}" if note else ""))
    bad = results["CHANGED"] or results["MINOR"] or results["PLACEHOLDER"]
    print("\nRESULT:", "NOT VERBATIM: fix the page or get the requester's confirmation" if bad else "TEXT COPIED VERBATIM (check ADDED text is wanted)")
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract")
    e.add_argument("mockup")
    e.add_argument("--out")
    p = sub.add_parser("placeholders")
    p.add_argument("mockup")
    c = sub.add_parser("compare")
    c.add_argument("mockup")
    c.add_argument("page")
    c.add_argument("--fills")
    args = ap.parse_args()
    return {"extract": cmd_extract, "placeholders": cmd_placeholders, "compare": cmd_compare}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
