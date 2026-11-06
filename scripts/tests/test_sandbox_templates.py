"""Real CLI policy checks in disposable Git repositories, never this checkout."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


CHECKER = Path(__file__).resolve().parents[1] / "sandbox_check.py"


class SandboxTemplateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "scripts").mkdir()
        shutil.copy2(CHECKER, self.root / "scripts/sandbox_check.py")
        self.git("init", "-q")
        self.git("config", "user.name", "Sandbox Test")
        self.git("config", "user.email", "sandbox@example.invalid")
        self.git("add", ".")
        self.git("commit", "-qm", "checker fixture")
        self.git("tag", "baseline")

    def git(self, *args):
        return subprocess.run(
            ["git", "-C", str(self.root), *args], check=True,
            capture_output=True, text=True,
        ).stdout

    def write(self, path, content):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def check(self):
        self.git("add", "-A")
        self.git("commit", "-qm", "sandbox change")
        result = subprocess.run(
            [sys.executable, str(self.root / "scripts/sandbox_check.py"),
             "--base", "baseline", "--json"],
            cwd=self.root, capture_output=True, text=True,
        )
        self.assertEqual(result.stderr, "")
        return result.returncode, json.loads(result.stdout)

    def make_baseline(self):
        self.git("add", "-A")
        self.git("commit", "-qm", "live site fixture")
        self.git("tag", "-f", "baseline")

    def test_deleting_existing_template_is_blocked(self):
        self.write("_includes/header.html", "<header>Live site</header>")
        self.make_baseline()
        (self.root / "_includes/header.html").unlink()
        code, report = self.check()
        self.assertEqual(code, 1, report)
        self.assertIn("deleted", " ".join(report["blocking"]))
        self.assertIn("_includes/header.html", " ".join(report["blocking"]))

    def test_pages_can_select_new_safe_layout(self):
        self.write("_layouts/default.html", "<main>{{ content }}</main>")
        page = "---\nlayout: default\nlang: en\ntitle: About\ndescription: About us\n---\n<p>About</p>"
        self.write("about.html", page)
        self.make_baseline()
        self.write("_layouts/article.liquid", "{% include header.html %}<article>{{ content }}</article>")
        self.write("about.html", page.replace("layout: default", "layout: article"))
        self.write("new.html", page.replace("layout: default", "layout: article"))
        code, report = self.check()
        self.assertEqual(code, 0, report)
        self.assertTrue(any("about.html → /about/" in item for item in report["changes"]))
        self.assertTrue(any("new.html → /new/" in item for item in report["changes"]))

    def test_pages_reject_missing_unsafe_or_traversal_layouts(self):
        self.write("_layouts/regular.html", "{{ content }}")
        self.write("_layouts/build.py", "print('not a layout')")
        self.write("_includes/header.html", "<header>Header</header>")
        (self.root / "_layouts/linked.html").symlink_to("regular.html")
        self.make_baseline()
        self.write("_layouts/unsafe.html", "<script>evil()</script>{{ content }}")
        layouts = ["missing", "../_includes/header", "/regular", "regular.html",
                   "{{ site.layout }}", "build", "linked", "unsafe", None, ["regular"]]
        for index, layout in enumerate(layouts):
            self.write(f"invalid-{index}.html", "---\nlayout: " + json.dumps(layout) +
                       "\nlang: en\ntitle: Test\ndescription: Test\n---\n<p>Test</p>")
        code, report = self.check()
        self.assertEqual(code, 1, report)
        for index, layout in enumerate(layouts):
            with self.subTest(layout=layout):
                self.assertTrue(any(item.startswith(f"invalid-{index}.html:") and "layout" in item
                                    for item in report["blocking"]), report)

    def test_template_symlinks_are_blocked(self):
        self.write("safe.html", "<p>Not a template</p>")
        self.write("_includes/existing.html", "<p>Old header</p>")
        self.make_baseline()
        existing = self.root / "_includes/existing.html"
        existing.unlink()
        existing.symlink_to("../safe.html")
        (self.root / "_includes/new.html").symlink_to("../safe.html")
        code, report = self.check()
        self.assertEqual(code, 1, report)
        for name in ("existing", "new"):
            self.assertTrue(any(f"_includes/{name}.html" in item and "symlink" in item
                                for item in report["blocking"]), report)

    def test_template_update_reorders_content_with_unchanged_legacy_scripts(self):
        scripts = ['<script src="/assets/js/site.js"></script>',
                   '<script>window.siteReady = true;</script>']
        self.write("_layouts/default.html", "\n".join([
            "<main>{{ content }}</main>", *scripts,
            "{% include header.html %}", "{% include footer.html %}",
        ]))
        self.make_baseline()
        self.write("_layouts/default.html", "\n".join([
            "{% include footer.html %}", *reversed(scripts),
            "<main><h1>New heading</h1>{{ content }}</main>",
            "{% include header.html %}",
        ]))
        code, report = self.check()
        self.assertEqual(code, 0, report)
        self.assertIn("Template changed: _layouts/default.html", report["changes"])

    def test_template_updates_cannot_replace_or_duplicate_legacy_code(self):
        cases = {
            "inline_body": ('<script>safe();</script>', '<script>evil();</script>'),
            "external_src": ('<script src="/old.js"></script>', '<script src="/new.js"></script>'),
            "script_attrs": ('<script defer src="/old.js"></script>', '<script src="/old.js"></script>'),
            "extra_script": ('<script>safe();</script>', '<script>safe();</script><script>evil();</script>'),
            "duplicate_script": ('<script>safe();</script>', '<script>safe();</script><script>safe();</script>'),
            "unclosed_body": ('<script>safe();', '<script>evil();'),
            "handler": ('<button onclick="safe()">Old</button>', '<button onclick="evil()">New</button>'),
            "js_url": ('<a href="javascript:safe()">Old</a>', '<a href="javascript:evil()">New</a>'),
        }
        for name, (before, _) in cases.items():
            self.write(f"_includes/{name}.html", before)
        self.make_baseline()
        for name, (_, after) in cases.items():
            self.write(f"_includes/{name}.html", after)
        code, report = self.check()
        self.assertEqual(code, 1, report)
        for name in cases:
            with self.subTest(change=name):
                self.assertTrue(any(f"_includes/{name}.html:" in item
                                    for item in report["blocking"]), report)

    def test_new_templates_block_unsafe_markup(self):
        payloads = {
            "script": '<script src="/assets/js/extra.js"></script>',
            "inline_script": '<script>alert(1)</script>',
            "unclosed_script": '<script>alert(1)',
            "event": '<button onclick="alert(1)">Click</button>',
            "url": '<a href="javascript:alert(1)">Click</a>',
            "encoded_url": '<a href="java&#x73;cript:alert(1)">Click</a>',
            "spaced_url": '<a href="java&#10;script:alert(1)">Click</a>',
            "object": '<object data="/payload"></object>',
            "embed": '<embed src="/payload">',
            "frame": '<iframe src="https://example.invalid"></iframe>',
            "style": '<style>body { display:none }</style>',
            "form": '<form action="https://example.invalid"></form>',
            "base": '<base href="https://example.invalid">',
        }
        for name, payload in payloads.items():
            self.write(f"_includes/{name}.html", payload)
        code, report = self.check()
        self.assertEqual(code, 1, report)
        for name in payloads:
            with self.subTest(payload=name):
                self.assertTrue(any(f"_includes/{name}.html:" in item
                                    for item in report["blocking"]), report)

    def test_new_layouts_accept_template_extensions_and_optional_frontmatter(self):
        for ext in ("html", "liquid", "md", "markdown"):
            self.write(f"_layouts/nested/article.{ext}", """---
layout: default
---
<!doctype html><html><head>
<meta charset="utf-8"><meta name="description" content="{{ page.description }}">
<link rel="stylesheet" href="{{ '/assets/css/site.css' | relative_url }}">
</head><body>{% include header.html %}{{ content }}</body></html>
""")
        code, report = self.check()
        self.assertEqual(code, 0, report)
        self.assertEqual(len(report["changes"]), 4)
        self.assertEqual(report["spanish"], [])

    def test_unrelated_paths_remain_prohibited(self):
        paths = [
            "_includes/build.py", "_layouts/build.py", "_layouts/config.yml",
            "_includes/theme.css", "_includes/code.js", "_includes/payload.svg",
            "_layouts/readme.txt", "_plugins/plugin.rb", "_config.yml",
            "scripts/build.py", ".github/workflows/site.yml", "data/news.json",
            "_posts/2026-11-04-news.md", "assets/css/site.css", "assets/js/site.js",
        ]
        for path in paths:
            self.write(path, "prohibited change")
        code, report = self.check()
        self.assertEqual(code, 1, report)
        for path in paths:
            with self.subTest(path=path):
                self.assertTrue(any(path in item for item in report["blocking"]), report)
        self.assertTrue(any("#news" in item for item in report["blocking"]))

    def test_page_protected_settings_and_deletion_remain_blocked(self):
        self.write("_layouts/default.html", "{{ content }}")
        page = "---\nlayout: default\nlang: en\ntitle: Test\ndescription: Test\n---\n<p>Test</p>"
        protected = {"css": "extra.css", "scripts": "extra.js", "nav": "extra",
                     "is_home": "true", "permalink": "/other/", "lang": "es"}
        for key in protected:
            self.write(f"setting-{key}.html", page)
        self.write("deleted.html", page)
        self.make_baseline()
        for key, value in protected.items():
            changed = page.replace("lang: en", "lang: es") if key == "lang" else page.replace(
                "layout: default", f"layout: default\n{key}: {value}")
            self.write(f"setting-{key}.html", changed)
        (self.root / "deleted.html").unlink()
        self.write("unsafe-page.html", page + '<script>evil();</script>{% include secret.html %}')
        code, report = self.check()
        self.assertEqual(code, 1, report)
        for key in protected:
            self.assertTrue(any(f"setting-{key}.html:" in item and repr(key) in item
                                for item in report["blocking"]), report)
        self.assertTrue(any("deleted.html" in item and "deleted" in item for item in report["blocking"]))
        self.assertTrue(any("unsafe-page.html:" in item and "script" in item for item in report["blocking"]))
        self.assertTrue(any("unsafe-page.html:" in item and "Liquid" in item for item in report["blocking"]))

    def test_pages_select_existing_layout_extensions_with_legacy_scripts(self):
        for ext in ("html", "liquid", "md", "markdown"):
            self.write(f"_layouts/article-{ext}.{ext}",
                       '<script src="/assets/js/site.js"></script>{{ content }}')
        self.make_baseline()
        for ext in ("html", "liquid", "md", "markdown"):
            self.write(f"article-{ext}.html", f"---\nlayout: article-{ext}\nlang: en\n"
                       "title: Test\ndescription: Test\n---\n<p>Test</p>")
        code, report = self.check()
        self.assertEqual(code, 0, report)

    def test_template_rename_cannot_delete_live_template(self):
        self.write("_includes/old.html", "<header>Live header</header>")
        self.make_baseline()
        (self.root / "_includes/old.html").rename(self.root / "_includes/new.html")
        code, report = self.check()
        self.assertEqual(code, 1, report)
        self.assertTrue(any("_includes/old.html" in item and "deleted" in item
                            for item in report["blocking"]), report)

    def test_new_include_accepts_liquid_without_page_frontmatter(self):
        self.write("_includes/cards.html", """{% assign cards = site.data.cards %}
{% capture heading %}Our community{% endcapture %}
{% if cards %}<h2>{{ heading }}</h2>{% endif %}
{% for card in cards %}{% include card.html card=card %}{% endfor %}
""")
        code, report = self.check()
        self.assertEqual(code, 0, report)
        self.assertEqual(report["blocking"], [])
        self.assertIn("Template added: _includes/cards.html", report["changes"])
        warning = " ".join(report["warnings"])
        self.assertIn("English", warning)
        self.assertIn("Spanish", warning)
        self.assertIn("rendered pages", warning)
        self.assertNotIn("→", " ".join(report["changes"]))


if __name__ == "__main__":
    unittest.main()
