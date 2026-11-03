#!/usr/bin/env python3
"""Visual check of sandbox pages: screenshots and layout problems.

  python3 scripts/sandbox_screens.py --sandbox https://forabrighterevanston.org/sandbox/<id>/ \
      --live https://forabrighterevanston.org/ --out /tmp/sandbox-shots  /home/faq/ /es/preguntas/ ...

For each page path, at a desktop width (1280 px) and a phone width (390 px), it
saves a full-page screenshot of the sandbox version (and of the live version,
when the page already exists there) and reports:

  - the page didn't load, or JavaScript errors in the browser console
  - sideways scrolling (something wider than the screen)
  - images that failed to load or have no alt text
  - text smaller than 12 px, and buttons/links smaller than 32 px tall on phones
  - more than one <h1>, or none

Look at the screenshots yourself as well; this catches mechanical problems,
not whether something looks good.

Needs Playwright:  pip install playwright && python3 -m playwright install chromium
"""
import argparse
import json
import sys
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Playwright isn't installed. Run: pip install playwright && python3 -m playwright install chromium")
    sys.exit(2)

PROBE = r"""
() => {
  const out = {};
  const de = document.documentElement;
  out.overflow = de.scrollWidth > window.innerWidth + 1 ? de.scrollWidth : 0;
  out.wide = [];
  if (out.overflow) {
    for (const el of document.querySelectorAll('body *')) {
      const r = el.getBoundingClientRect();
      if (r.right > window.innerWidth + 1 && r.width > 0) {
        out.wide.push((el.tagName.toLowerCase() + (el.className && typeof el.className === 'string' ? '.' + el.className.split(' ')[0] : '')));
        if (out.wide.length > 5) break;
      }
    }
  }
  out.brokenImages = [...document.images].filter(i => i.getAttribute('src') && i.complete && i.naturalWidth === 0).map(i => i.getAttribute('src'));
  out.noAlt = [...document.images].filter(i => i.getAttribute('src') && !i.hasAttribute('alt')).map(i => i.getAttribute('src'));
  out.h1 = document.querySelectorAll('h1').length;
  out.tinyText = 0;
  const walker = document.createTreeWalker(document.querySelector('main') || document.body, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const n = walker.currentNode;
    if (!n.textContent.trim()) continue;
    const el = n.parentElement; const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || el.closest('.visually-hidden')) continue;
    if (parseFloat(cs.fontSize) < 12) out.tinyText++;
  }
  out.smallTargets = [...document.querySelectorAll('main a, main button')].filter(el => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && r.height < 32 && !el.closest('p, li, td, figcaption');
  }).length;
  return out;
}
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sandbox", required=True)
    ap.add_argument("--live")
    ap.add_argument("--out", default="/tmp/sandbox-shots")
    ap.add_argument("paths", nargs="+")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    sb = args.sandbox.rstrip("/")
    live = args.live.rstrip("/") if args.live else None
    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        for width, label in ((1280, "desktop"), (390, "phone")):
            ctx = browser.new_context(viewport={"width": width, "height": 900 if width > 600 else 800},
                                      is_mobile=width < 600, has_touch=width < 600)
            for path in args.paths:
                path = "/" + path.lstrip("/")
                for which, base in (("sandbox", sb), ("live", live)):
                    if not base:
                        continue
                    page = ctx.new_page()
                    errors = []
                    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
                    page.on("pageerror", lambda e: errors.append(str(e)))
                    url = base + path
                    try:
                        resp = page.goto(url, wait_until="networkidle", timeout=45000)
                        code = resp.status if resp else 0
                    except Exception as e:
                        code, errors = 0, errors + [str(e)]
                    name = f"{which}-{label}-{path.strip('/').replace('/', '_') or 'home'}.png"
                    item = {"page": path, "version": which, "screen": label, "status": code, "screenshot": str(out / name)}
                    if code == 200:
                        page.wait_for_timeout(600)
                        page.screenshot(path=str(out / name), full_page=True)
                        item.update(page.evaluate(PROBE))
                    item["consoleErrors"] = errors[:5]
                    page.close()
                    if which == "live" and code == 404:
                        continue  # new page: nothing to compare with
                    results.append(item)
            ctx.close()
        browser.close()

    problems = []
    for r in results:
        if r["version"] != "sandbox":
            continue
        where = f'{r["page"]} ({r["screen"]})'
        if r["status"] != 200:
            problems.append(f"{where}: didn't load (HTTP {r['status']})")
            continue
        if r.get("overflow"):
            problems.append(f"{where}: scrolls sideways ({r['overflow']} px wide); too wide: {', '.join(r.get('wide', []))}")
        if r.get("brokenImages"):
            problems.append(f"{where}: images didn't load: {', '.join(map(str, r['brokenImages']))}")
        if r.get("noAlt"):
            problems.append(f"{where}: images without alt text: {', '.join(map(str, r['noAlt']))}")
        if r.get("h1") != 1:
            problems.append(f"{where}: {r.get('h1')} main headings (<h1>); there should be exactly 1")
        if r.get("tinyText"):
            problems.append(f"{where}: {r['tinyText']} pieces of text smaller than 12 px")
        if r["screen"] == "phone" and r.get("smallTargets"):
            problems.append(f"{where}: {r['smallTargets']} buttons/links shorter than 32 px (hard to tap)")
        if r.get("consoleErrors"):
            problems.append(f"{where}: browser errors: {' | '.join(r['consoleErrors'])}")

    print(json.dumps({"screenshots": out.as_posix(), "problems": problems, "pages": results}, indent=2, ensure_ascii=False))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
