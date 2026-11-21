"""Pledge text files: wording is editable in #website updates; settings are locked."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


CHECKER = Path(__file__).resolve().parents[1] / "sandbox_check.py"

PLEDGE = """endpoint: "https://script.google.com/macros/s/EXAMPLE/exec"
turnstile_sitekey: ""
mailchimp:
  form: "https://example.us9.list-manage.com/subscribe/post?u=a&id=b"
  honeypot: b_a_b
  tags: "123"
en:
  button: I pledge
  thanks: Thank you. Now ask two neighbors to pledge with you.
  page_url: /pledge/
  embed_url: /pledge/embed/
  privacy_url: /privacy/
es:
  button: Me comprometo
  thanks: Gracias. Ahora invita a dos vecinos a comprometerse contigo.
  page_url: /es/compromiso/
  embed_url: /es/compromiso/insertar/
  privacy_url: /es/privacidad/
"""

PAGE = """en:
  why_label: Why a pledge
  ways:
    - title: Sign the pledge
      url: "#pledge"
es:
  why_label: Por qué un compromiso
  ways:
    - title: Firma el compromiso
      url: "#pledge"
sources:
  - label: Evanston RoundTable
    url: https://evanstonroundtable.com/example
"""

GUIDE = """en:
  copy: Copy code
es:
  copy: Copiar código
"""


class PledgeTextFileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.write("scripts/sandbox_check.py", CHECKER.read_text())
        self.write("_data/pledge.yml", PLEDGE)
        self.write("_data/pledge_page.yml", PAGE)
        self.write("_data/pledge_embed.yml", GUIDE)
        self.git("init", "-q")
        self.git("config", "user.name", "Pledge Test")
        self.git("config", "user.email", "pledge@example.invalid")
        self.git("add", "-A")
        self.git("commit", "-qm", "fixture")
        self.git("tag", "-f", "baseline")

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args],
                              check=True, capture_output=True, text=True).stdout

    def write(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def edit(self, path, old, new):
        target = self.root / path
        text = target.read_text(encoding="utf-8")
        self.assertIn(old, text)
        target.write_text(text.replace(old, new, 1), encoding="utf-8")

    def check(self):
        self.git("add", "-A")
        self.git("commit", "-qm", "update")
        result = subprocess.run([sys.executable, str(self.root / "scripts/sandbox_check.py"),
                                 "--base", "baseline", "--json"],
                                cwd=self.root, capture_output=True, text=True)
        self.assertEqual(result.stderr, "")
        return result.returncode, json.loads(result.stdout)

    def test_wording_in_both_languages_is_ok(self):
        self.edit("_data/pledge.yml", "  thanks: Thank you.", "  thanks: Thank you!")
        self.edit("_data/pledge.yml", "  thanks: Gracias.", "  thanks: ¡Gracias!")
        self.edit("_data/pledge_page.yml", "why_label: Why a pledge", "why_label: Why this pledge")
        self.edit("_data/pledge_page.yml", "why_label: Por qué un compromiso", "why_label: Por qué este compromiso")
        self.edit("_data/pledge_embed.yml", "copy: Copy code", "copy: Copy the code")
        self.edit("_data/pledge_embed.yml", "copy: Copiar código", "copy: Copiar el código")
        code, report = self.check()
        self.assertEqual(report["blocking"], [])
        self.assertEqual(code, 0)
        self.assertTrue(any("both English and Spanish" in s for s in report["spanish"]))

    def test_one_language_only_is_flagged_but_not_blocked(self):
        self.edit("_data/pledge.yml", "  thanks: Thank you.", "  thanks: Thank you!")
        code, report = self.check()
        self.assertEqual(report["blocking"], [])
        self.assertTrue(any("one language only" in s and "en.thanks" in s for s in report["spanish"]))

    def test_settings_are_locked(self):
        cases = [
            ("_data/pledge.yml", 'endpoint: "https://script.google.com/macros/s/EXAMPLE/exec"',
             'endpoint: "https://attacker.invalid/exec"', "endpoint"),
            ("_data/pledge.yml", 'turnstile_sitekey: ""', 'turnstile_sitekey: "x"', "turnstile_sitekey"),
            ("_data/pledge.yml", 'tags: "123"', 'tags: "999"', "mailchimp.tags"),
            ("_data/pledge.yml", "list-manage.com/subscribe/post?u=a&id=b",
             "list-manage.com/subscribe/post?u=z&id=b", "mailchimp.form"),
            ("_data/pledge.yml", "  page_url: /pledge/", "  page_url: /elsewhere/", "en.page_url"),
            ("_data/pledge.yml", "  privacy_url: /es/privacidad/", "  privacy_url: /x/", "es.privacy_url"),
            ("_data/pledge_page.yml", "url: https://evanstonroundtable.com/example",
             "url: https://attacker.invalid/", "sources[0].url"),
            ("_data/pledge_page.yml", '      url: "#pledge"', '      url: "https://attacker.invalid/"', "en.ways[0].url"),
        ]
        for path, old, new, key in cases:
            with self.subTest(key=key):
                self.git("reset", "-q", "--hard", "baseline")
                self.edit(path, old, new)
                code, report = self.check()
                self.assertEqual(code, 1)
                self.assertTrue(any(f"{path} → {key}: this is a pledge setting" in b for b in report["blocking"]),
                                report["blocking"])

    def test_code_and_new_settings_are_blocked(self):
        self.edit("_data/pledge.yml", "  thanks: Thank you.", "  thanks: <script>alert(1)</script>")
        code, report = self.check()
        self.assertEqual(code, 1)
        self.assertTrue(any("contains code" in b for b in report["blocking"]))
        self.git("reset", "-q", "--hard", "baseline")
        self.edit("_data/pledge.yml", "  button: I pledge\n", "  button: I pledge\n  extra: hi\n")
        code, report = self.check()
        self.assertEqual(code, 1)
        self.assertTrue(any("settings were added or removed" in b for b in report["blocking"]))

    def test_files_cannot_be_deleted(self):
        (self.root / "_data/pledge_embed.yml").unlink()
        code, report = self.check()
        self.assertEqual(code, 1)
        self.assertTrue(any("can be edited but not deleted" in b for b in report["blocking"]))


if __name__ == "__main__":
    unittest.main()
