"""Owner-approved site update: campaign.css and the hearing calendar files,
only in sandbox/home-hearings-resources."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


CHECKER = Path(__file__).resolve().parents[1] / "sandbox_check.py"
CSS = ".cx-header { color: #fff; }\n@media (max-width: 600px) { .cx-nav a, .cx-hero .pl-foot { gap: 4px; } }\n"
ICS = "\r\n".join([
    "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Test//EN", "BEGIN:VEVENT", "UID:a@example.invalid",
    "DTSTAMP:20261124T220000Z", "DTSTART:20261201T231500Z", "DTEND:20261202T034500Z",
    "SUMMARY:Hearing", "LOCATION:1500 McDaniel Ave.\\, Evanston",
    "URL:https://forabrighterevanston.org/hearings/", "END:VEVENT", "END:VCALENDAR", ""])
ICS_PATH = "assets/files/d65-closure-hearing-2026-12-01.ics"


class SiteUpdateFileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.write("scripts/sandbox_check.py", CHECKER.read_text())
        self.write("index.html", "---\nlayout: default\nlang: en\ntitle: Home\n---\n<p>Hi</p>\n")
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "Site Update Test")
        self.git("config", "user.email", "site-update@example.invalid")
        self.git("add", "-A")
        self.git("commit", "-qm", "fixture")
        self.git("tag", "-f", "baseline")
        self.git("checkout", "-q", "-b", "sandbox/home-hearings-resources")

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args],
                              check=True, capture_output=True, text=True).stdout

    def write(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="")

    def check(self):
        self.git("add", "-A")
        self.git("commit", "-qm", "update")
        result = subprocess.run([sys.executable, str(self.root / "scripts/sandbox_check.py"),
                                 "--base", "baseline", "--json"],
                                cwd=self.root, capture_output=True, text=True)
        self.assertEqual(result.stderr, "")
        return result.returncode, json.loads(result.stdout)

    def test_approved_files_pass_in_their_sandbox(self):
        self.write("assets/css/campaign.css", CSS)
        self.write(ICS_PATH, ICS)
        code, report = self.check()
        self.assertEqual(report["blocking"], [])
        self.assertEqual(code, 0)

    def test_other_sandboxes_stay_blocked(self):
        self.git("checkout", "-q", "-b", "sandbox/other-update")
        self.write("assets/css/campaign.css", CSS)
        self.write(ICS_PATH, ICS)
        code, report = self.check()
        self.assertEqual(code, 1)
        self.assertTrue(any("part of the site's structure" in b for b in report["blocking"]))
        self.assertTrue(any(".ics files aren't allowed" in b for b in report["blocking"]))

    def test_other_paths_stay_blocked(self):
        self.write("assets/css/other.css", CSS)
        self.write("assets/files/other.ics", ICS)
        code, report = self.check()
        self.assertEqual(code, 1)
        self.assertEqual(len(report["blocking"]), 2, report["blocking"])

    def test_unsafe_css_is_blocked(self):
        for css in ("body { color: red; }\n", ".cx-a { background: url(https://x.invalid/a.png); }\n",
                    "@import 'x.css';\n", ".cx-a + .x { color: red; }\n", ".cx-a { content: '\\41'; }\n"):
            with self.subTest(css=css):
                self.git("reset", "-q", "--hard", "baseline")
                self.write("assets/css/campaign.css", css)
                code, report = self.check()
                self.assertEqual(code, 1)
                self.assertTrue(any(b.startswith("assets/css/campaign.css:") for b in report["blocking"]),
                                report["blocking"])

    def test_unsafe_calendar_is_blocked(self):
        cases = (ICS.replace("SUMMARY:Hearing", "ATTACH:https://x.invalid/a.exe"),
                 ICS.replace("URL:https://forabrighterevanston.org/hearings/", "URL:https://x.invalid/"),
                 ICS.replace("END:VCALENDAR", "BEGIN:VALARM\r\nEND:VALARM\r\nEND:VCALENDAR"),
                 "<script>alert(1)</script>")
        for ics in cases:
            with self.subTest(ics=ics[:40]):
                self.git("reset", "-q", "--hard", "baseline")
                self.write(ICS_PATH, ics)
                code, report = self.check()
                self.assertEqual(code, 1)
                self.assertTrue(any(b.startswith(ICS_PATH + ":") for b in report["blocking"]), report["blocking"])

    def test_deletion_is_not_authorized(self):
        self.git("checkout", "-q", "main")
        self.write("assets/css/campaign.css", CSS)
        self.git("add", "-A")
        self.git("commit", "-qm", "live css")
        self.git("tag", "-f", "baseline")
        self.git("checkout", "-q", "-B", "sandbox/home-hearings-resources")
        (self.root / "assets/css/campaign.css").unlink()
        code, report = self.check()
        self.assertEqual(code, 1)
        self.assertTrue(any("deletion is not authorized" in b for b in report["blocking"]), report["blocking"])


if __name__ == "__main__":
    unittest.main()
