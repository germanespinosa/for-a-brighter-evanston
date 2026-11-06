"""Sharing policy integration tests: real CLI, Git fixtures and local HTTP."""
import json
from contextlib import contextmanager
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


CHECKER = Path(__file__).resolve().parents[1] / "sandbox_check.py"


class SharingCardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.write("scripts/sandbox_check.py", CHECKER.read_text())
        self.write("_layouts/default.html", "<main>{{ content }}</main>")
        self.git("init", "-q")
        self.git("config", "user.name", "Sharing Test")
        self.git("config", "user.email", "sharing@example.invalid")
        self.baseline()

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args],
                              check=True, capture_output=True, text=True).stdout

    def write(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def page(self, path="topic/index.html", **overrides):
        fields = dict(layout="default", lang="en", title="Our topic",
                      description="Learn about our topic.")
        fields.update(overrides)
        self.write(path, "---\n" + "\n".join(f"{k}: {json.dumps(v)}" for k, v in fields.items())
                   + "\n---\n<p>Topic content</p>\n")

    def baseline(self):
        self.git("add", "-A")
        self.git("commit", "-qm", "fixture")
        self.git("tag", "-f", "baseline")

    def check(self, *args, stdlib=False, commit=True):
        if commit:
            self.git("add", "-A")
            self.git("commit", "-qm", "update")
        result = subprocess.run([sys.executable, *(["-S"] if stdlib else []),
                                 str(self.root / "scripts/sandbox_check.py"),
                                 "--base", "baseline", "--json", *args],
                                cwd=self.root, capture_output=True, text=True)
        self.assertEqual(result.stderr, "")
        return result.returncode, json.loads(result.stdout)

    def image(self, path="assets/img/topic.png"):
        import base64
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII="))

    def test_new_share_image_must_be_safe_new_tracked_local_image(self):
        self.image("assets/img/old.png")
        self.write("_data/i18n/en.yml", "home:\n  share_image: /assets/img/home.png\n")
        self.image("assets/img/home.png")
        self.baseline()
        self.image()
        self.write("assets/img/document.pdf", "PDF")
        (self.root / "assets/img/linked.png").symlink_to("topic.png")
        (self.root / "assets/img/alias").symlink_to(".", target_is_directory=True)
        (self.root / "assets/img/directory.png").mkdir()
        invalid = ["/assets/img/missing.png", "/assets/img/old.png", "/assets/img/home.png",
                   "https://example.invalid/card.png", "//example.invalid/card.png",
                   "/assets/img/../img/topic.png", "/assets/img/%2e%2e/topic.png",
                   "/assets/img/topic.png?x=1", "assets/img/topic.png", "/assets/files/topic.png",
                   "/assets/img/document.pdf", "/assets/img/linked.png", "/assets/img/directory.png",
                   "/assets/img/alias/topic.png", "/assets/img/topic.png#card"]
        for index, value in enumerate(invalid):
            self.page(f"invalid-{index}.html", share_image=value)
        self.page("valid.md", share_image="/assets/img/topic.png")
        code, report = self.check()
        self.assertEqual(code, 1, report)
        for index, value in enumerate(invalid):
            with self.subTest(value=value):
                self.assertTrue(any(item.startswith(f"invalid-{index}.html:") and "share_image" in item
                                    for item in report["blocking"]), report)
        self.assertFalse(any(item.startswith("valid.md:") for item in report["blocking"]), report)

    def test_title_description_require_strings_with_and_without_pyyaml(self):
        self.image()
        invalid = [None, False, True, [], ["words"], {}, 12, 1.5, "", "  "]
        for key in ("title", "description"):
            for index, value in enumerate(invalid):
                self.page(f"{key}-{index}.html", share_image="/assets/img/topic.png", **{key: value})
        for stdlib in (False, True):
            with self.subTest(stdlib=stdlib):
                code, report = self.check(stdlib=stdlib, commit=not stdlib)
                self.assertEqual(code, 1, report)
                for key in ("title", "description"):
                    for index in range(len(invalid)):
                        self.assertTrue(any(item.startswith(f"{key}-{index}.html:") and key in item
                                            for item in report["blocking"]), f"{key}-{index}: {report}")

    def test_bilingual_pages_can_share_neutral_new_card_but_require_visual_review(self):
        self.image()
        self.page(share_image="/assets/img/topic.png", alt_url="/es/tema/")
        self.page("es/tema/index.md", lang="es", title="Nuestro tema",
                  description="Aprenda sobre nuestro tema.", alt_url="/topic/",
                  share_image="/assets/img/topic.png")
        for stdlib in (False, True):
            code, report = self.check(stdlib=stdlib, commit=not stdlib)
            self.assertEqual(code, 0, report)
            warning = " ".join(report["warnings"])
            self.assertIn("sharing card", warning)
            self.assertIn("review", warning)
            self.assertIn("localized", warning)
            self.assertIn("1200", warning)

    def test_existing_page_edit_does_not_require_share_image(self):
        self.page()
        self.baseline()
        self.page(title="Edited title")
        code, report = self.check()
        self.assertEqual(code, 0, report)
        self.assertFalse(any("share_image" in item for item in report["blocking"]))

    def test_untracked_card_does_not_satisfy_new_page(self):
        self.page(share_image="/assets/img/topic.png")
        self.git("add", "topic/index.html")
        self.git("commit", "-qm", "page without card")
        self.image()
        code, report = self.check(commit=False)
        self.assertEqual(code, 1, report)
        self.assertTrue(any("share_image" in item and "tracked and added" in item for item in report["blocking"]), report)

    def test_same_update_generic_fallback_is_rejected_without_pyyaml(self):
        self.write("_data/i18n/es.yml", "home:\n  share_image: '/assets/img/topic.png' # home card\n")
        self.image()
        self.page(share_image="/assets/img/topic.png")
        code, report = self.check(stdlib=True)
        self.assertEqual(code, 1, report)
        self.assertTrue(any("share_image" in item and "generic" in item for item in report["blocking"]), report)

    def test_share_card_retains_existing_media_size_limits(self):
        self.image()
        (self.root / "assets/img/topic.png").write_bytes(b"x" * (5 * 1024 * 1024 + 1))
        self.page(share_image="/assets/img/topic.png")
        code, report = self.check()
        self.assertEqual(code, 1, report)
        self.assertTrue(any("assets/img/topic.png" in item and "limit is 5 MB" in item for item in report["blocking"]), report)

    @contextmanager
    def server(self):
        routes, requests = {}, []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append((self.command, self.path))
                status, mime, body = routes.get(self.path, (404, "text/plain", b"missing"))
                self.send_response(status)
                self.send_header("Content-Type", mime)
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}/sandbox/check/"
        routes["/sandbox/check/"] = (200, "text/html", b"<p>Home</p>")
        try:
            yield base, routes, requests
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def rendered_card(self, base, **overrides):
        metadata = {"og:title": "Our topic", "og:description": "Learn about our topic.",
                    "og:image": base + "assets/img/topic.png", "twitter:card": "summary_large_image"}
        metadata.update(overrides)
        return ("<html><head>" + "".join(
            f'<meta {"name" if key.startswith("twitter:") else "property"}="{key}" content="{escape(value, quote=True)}">'
            for key, value in metadata.items() if value is not None
        ) + "</head><body>Topic</body></html>").encode()

    def test_deployed_new_page_missing_sharing_metadata_is_blocked(self):
        self.image()
        self.page(share_image="/assets/img/topic.png")
        with self.server() as (base, routes, requests):
            routes["/sandbox/check/topic/"] = (200, "text/html", b"<p>Topic</p>")
            code, report = self.check("--url", base)
        self.assertEqual(code, 1, report)
        for key in ("og:title", "og:description", "og:image", "twitter:card"):
            self.assertTrue(any(key in item for item in report["blocking"]), report)

    def test_deployed_card_image_must_load_with_image_mime(self):
        self.image()
        self.page(share_image="/assets/img/topic.png")
        with self.server() as (base, routes, requests):
            routes["/sandbox/check/topic/"] = (200, "text/html", self.rendered_card(base))
            code, report = self.check("--url", base)
            self.assertEqual(code, 1, report)
            self.assertTrue(any("sharing image" in item and "404" in item for item in report["blocking"]), report)
            for status, mime, body, expected_code in [
                (200, "text/html", b"<html>not an image</html>", 1),
                (200, "image/png", b"", 1),
                (200, "image/png", (self.root / "assets/img/topic.png").read_bytes(), 0),
            ]:
                with self.subTest(status=status, mime=mime, empty=not body):
                    routes["/sandbox/check/assets/img/topic.png"] = (status, mime, body)
                    code, report = self.check("--url", base, commit=False)
                    self.assertEqual(code, expected_code, report)
            self.assertIn(("GET", "/sandbox/check/assets/img/topic.png"), requests)

    def test_deployed_metadata_must_match_each_localized_page(self):
        self.image()
        title, description = 'Tema & "comunidad"', '<b>Aprenda</b> sobre el tema & más.'
        self.page("es/tema/index.md", lang="es", title=title, description=description,
                  share_image="/assets/img/topic.png")
        with self.server() as (base, routes, requests):
            routes["/sandbox/check/assets/img/topic.png"] = (
                200, "image/png", (self.root / "assets/img/topic.png").read_bytes())
            good = {"og:title": title, "og:description": "Aprenda sobre el tema & más."}
            routes["/sandbox/check/es/tema/"] = (200, "text/html", self.rendered_card(base, **good))
            code, report = self.check("--url", base.rstrip("/"))
            self.assertEqual(code, 0, report)
            cases = [(key, value) for key in ("og:title", "og:description", "og:image", "twitter:card")
                     for value in (None, "", "Wrong metadata")]
            cases += [("og:image", "/sandbox/check/assets/img/topic.png"),
                      ("og:image", base.replace("/sandbox/check/", "/") + "assets/img/topic.png")]
            for key, value in cases:
                with self.subTest(key=key, value=value):
                    values = {**good, key: value}
                    routes["/sandbox/check/es/tema/"] = (200, "text/html", self.rendered_card(base, **values))
                    code, report = self.check("--url", base, commit=False)
                    self.assertEqual(code, 1, report)
                    self.assertTrue(any(key in item for item in report["blocking"]), report)

    def test_existing_deployed_page_is_grandfathered(self):
        self.page()
        self.baseline()
        self.page(title="An existing page edit")
        with self.server() as (base, routes, requests):
            routes["/sandbox/check/topic/"] = (200, "text/html", b"<p>Legacy page without card</p>")
            code, report = self.check("--url", base)
        self.assertEqual(code, 0, report)

    def test_deployed_metadata_in_body_or_duplicated_is_blocked(self):
        self.image()
        self.page(share_image="/assets/img/topic.png")
        with self.server() as (base, routes, requests):
            routes["/sandbox/check/assets/img/topic.png"] = (
                200, "image/png", (self.root / "assets/img/topic.png").read_bytes())
            valid = self.rendered_card(base)
            invalid = [valid.replace(b"<head>", b"<body>").replace(b"</head>", b"</body>"),
                       valid.replace(b"</head>", b'<meta property="og:title" content="Our topic"></head>')]
            for index, html in enumerate(invalid):
                routes["/sandbox/check/topic/"] = (200, "text/html", html)
                code, report = self.check("--url", base, commit=index == 0)
                self.assertEqual(code, 1, report)
                self.assertTrue(any("og:title" in item for item in report["blocking"]), report)

    def test_dangling_share_image_symlink_blocks_without_crashing(self):
        (self.root / "assets/img").mkdir(parents=True)
        (self.root / "assets/img/topic.png").symlink_to("missing.png")
        self.page(share_image="/assets/img/topic.png")
        code, report = self.check()
        self.assertEqual(code, 1, report)
        self.assertTrue(any("share_image" in item for item in report["blocking"]), report)

    def test_new_pages_require_nonempty_share_image(self):
        self.page()
        for index, value in enumerate(("", "  ", None, False, ["/assets/img/topic.png"])):
            self.page(f"invalid-{index}.md", share_image=value)
        code, report = self.check()
        self.assertEqual(code, 1, report)
        for path in ["topic/index.html", *(f"invalid-{i}.md" for i in range(5))]:
            self.assertTrue(any(path in item and "share_image" in item for item in report["blocking"]), report)


if __name__ == "__main__":
    unittest.main()
