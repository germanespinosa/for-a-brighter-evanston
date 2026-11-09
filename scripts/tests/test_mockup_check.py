"""Tests for scripts/mockup_check.py (mockup text extraction, missing-information
detection and verbatim comparison)."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "mockup_check.py"

MOCKUP = """<!doctype html><html><head><title>t</title><style>h1{color:red}</style>
<script>document.write('not text')</script></head><body>
<nav><a href="#">Home</a></nav>
<h1>Join the DEC Rally</h1>
<p>Neighbors will gather on [day of the event] at 4 PM.</p>
<p>Bring a sign, bring a friend, and wear yellow!</p>
<p>Parking: TBD</p>
<a href="#">Sign up to volunteer</a>
<img src="https://via.placeholder.com/600" alt="Rally photo">
</body></html>"""

PAGE_OK = """<html><body><header>Site menu</header><main>
<h1>Join the DEC Rally</h1>
<p>Neighbors will gather on Saturday, November 14 at 4 PM.</p>
<p>Bring a sign, bring a friend, and wear yellow!</p>
<p>Parking: on McDaniel Ave.</p>
<a href="/volunteer/">Sign up to volunteer</a>
</main><footer>Footer</footer></body></html>"""


def run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)


class MockupCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        (self.dir / "mockup.html").write_text(MOCKUP, encoding="utf-8")
        (self.dir / "fills.json").write_text(json.dumps(
            {"[day of the event]": "Saturday, November 14", "TBD": "on McDaniel Ave."}), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def page(self, html):
        p = self.dir / "page.html"
        p.write_text(html, encoding="utf-8")
        return str(p)

    def test_extract_skips_code_and_marks_menu(self):
        out = run("extract", str(self.dir / "mockup.html")).stdout
        self.assertIn("Join the DEC Rally", out)
        self.assertNotIn("not text", out)
        self.assertNotIn("color:red", out)
        self.assertIn("Home  (mockup header/menu/footer)", out)

    def test_placeholders_found(self):
        r = run("placeholders", str(self.dir / "mockup.html"))
        self.assertEqual(r.returncode, 1)
        for expected in ("[day of the event]", "TBD", "no real destination", "placeholder image"):
            self.assertIn(expected, r.stdout)

    def test_verbatim_page_with_fills_passes(self):
        r = run("compare", str(self.dir / "mockup.html"), self.page(PAGE_OK), "--fills", str(self.dir / "fills.json"))
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("TEXT COPIED VERBATIM", r.stdout)

    def test_reworded_text_fails(self):
        r = run("compare", str(self.dir / "mockup.html"),
                self.page(PAGE_OK.replace("wear yellow!", "wear yellow.")), "--fills", str(self.dir / "fills.json"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("CHANGED", r.stdout)
        self.assertIn("ADDED", r.stdout)

    def test_case_change_is_minor_and_fails(self):
        r = run("compare", str(self.dir / "mockup.html"),
                self.page(PAGE_OK.replace("Sign up to volunteer", "sign up to volunteer")), "--fills", str(self.dir / "fills.json"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("MINOR", r.stdout)

    def test_unfilled_placeholder_fails(self):
        page = PAGE_OK.replace("Saturday, November 14", "[day of the event]")
        r = run("compare", str(self.dir / "mockup.html"), self.page(page))
        self.assertEqual(r.returncode, 1)
        self.assertIn("PLACEHOLDER", r.stdout)

    def test_site_header_and_footer_not_compared(self):
        r = run("compare", str(self.dir / "mockup.html"), self.page(PAGE_OK), "--fills", str(self.dir / "fills.json"))
        self.assertNotIn("Site menu", r.stdout)
        self.assertNotIn("'Footer'", r.stdout)

    def test_text_mockup(self):
        (self.dir / "mockup.txt").write_text("Join the DEC Rally\n\nNeighbors will gather on [day of the event] at 4 PM.\n", encoding="utf-8")
        r = run("compare", str(self.dir / "mockup.txt"), self.page(PAGE_OK), "--fills", str(self.dir / "fills.json"))
        self.assertEqual(r.returncode, 0, r.stdout)


if __name__ == "__main__":
    unittest.main()
