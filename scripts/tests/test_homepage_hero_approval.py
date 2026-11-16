import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

CHECKER = Path(__file__).resolve().parents[1] / 'sandbox_check.py'
CSS = 'assets/css/release-home.css'
JS = 'assets/js/hero-slideshow.js'
PAGES = ['index.html', 'es/index.html']
SOURCE = {'authorizer_id': 'DELEGATE_FIXTURE', 'source': {'channel_id': 'CHANNEL_FIXTURE',
          'message_ts': 'approval-fixture', 'question_ts': 'question-fixture'}}
OLD_LINK = "  {%- if page.url == '/home/voter-poll/' or page.url == '/es/encuesta/' %}\n"
NEW_LINK = ("  {%- if page.url == '/' or page.url == '/es/' %}\n"
            "  <link rel=\"stylesheet\" href=\"{{ '/assets/css/release-home.css' | relative_url }}\">\n"
            "  {%- elsif page.url == '/home/voter-poll/' or page.url == '/es/encuesta/' %}\n")
OLD_BODY = "{% if page.url == '/home/voter-poll/' or page.url == '/es/encuesta/' %} release-poll"
NEW_BODY = "{% if page.url == '/' or page.url == '/es/' %} release-home{% elsif page.url == '/home/voter-poll/' or page.url == '/es/encuesta/' %} release-poll"
MAINTENANCE = ['scripts/sandbox_check.py', 'scripts/tests/test_homepage_hero_approval.py',
               'docs/agents/fabian-website.md', 'docs/agents/fabian-website-cards.md',
               'docs/help/team-help.md', 'docs/help/team-help.pdf', 'docs/help/reviewed-sources.json',
               'scripts/tests/test_hero_slideshow.py']
TEMPLATE_BASE = b'<section>old hero</section>\n'
TEMPLATE_REVIEWED = b'<section>reviewed hero</section>\n'
PHOTO_NAMES = [f'assets/img/hero/heather-eidson-meetup-{n:02}.jpg' for n in range(1, 11)]
PHOTO_BYTES = {name: f'photo fixture {n}'.encode() for n, name in enumerate(PHOTO_NAMES, 1)}
DATA_REVIEWED = ''.join(f'- file: {Path(name).name}\n  position: "50% 50%"\n  width: 1600\n  height: 1000\n' for name in PHOTO_NAMES).encode()


class HomepageHeroApprovalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'repo'
        self.root.mkdir()
        self.git('init', '-q', '-b', 'main')
        self.git('config', 'user.name', 'Test')
        self.git('config', 'user.email', 'test@example.test')
        checker = CHECKER.read_bytes()
        bindings = {
            b'HERO_SOURCE_SHA256 = ': json.dumps(SOURCE, sort_keys=True, separators=(',', ':')).encode(),
            b'HERO_CSS: ': b'.release-home .hero { color: navy; }\n',
            b'HERO_SCRIPT: ': b'/* reviewed slideshow fixture */\n',
            b'HERO_TEMPLATE_BASE_SHA256 = ': TEMPLATE_BASE,
            b'HERO_TEMPLATE_SHA256 = ': TEMPLATE_REVIEWED,
            b'HERO_DATA_SHA256 = ': DATA_REVIEWED,
        }
        for key, data in bindings.items():
            checker, count = re.subn(re.escape(key) + b'"(?:UNREVIEWED|[a-f0-9]{64})"',
                                     key + b'"' + hashlib.sha256(data).hexdigest().encode() + b'"', checker)
            self.assertEqual(count, 1, key)
        photo_hashes = {name: hashlib.sha256(data).hexdigest() for name, data in PHOTO_BYTES.items()}
        checker, count = re.subn(rb'HERO_PHOTO_SHA256 = \{.*?\n\}',
                                 ('HERO_PHOTO_SHA256 = ' + repr(photo_hashes)).encode(), checker, flags=re.S)
        self.assertEqual(count, 1)
        self.write('scripts/sandbox_check.py', checker)
        self.write('_layouts/default.html', (OLD_LINK + OLD_BODY + '\n{{ content }}').encode())
        self.write('_includes/pages/home.html', TEMPLATE_BASE)
        self.write('_data/hero.yml', b'- file: old.jpg\n  position: "55% 40%"\n  width: 1600\n  height: 1067\n')
        self.write('_data/event.yml', b'show: true\n')
        self.write('data/news.json', b'{"news": ["original"]}\n')
        for lang, old in [('en', 'Photo by Joerg Metzner'), ('es', 'Foto de Joerg Metzner')]:
            self.write(f'_data/i18n/{lang}.yml', f'home:\n  photo_credit: {old}\n  headline: Original\n'.encode())
        self.write(CSS, b'.release-home { color: black; }\n')
        for name in MAINTENANCE[2:-1]:
            self.write(name, b'baseline\n')
        for name, lang in zip(PAGES, ['en', 'es']):
            self.write(name, ('---\nlayout: default\nlang: ' + lang + '\ntitle: Home\ndescription: Home\ncss: home.css\nscripts: [home.js]\n---\n<p>Home</p>\n').encode())
        self.git('add', '-A')
        self.git('commit', '-qm', 'base')
        self.base = self.git('rev-parse', 'HEAD').strip()
        self.git('update-ref', 'refs/remotes/origin/main', self.base)
        self.git('checkout', '-qb', 'sandbox/homepage-hero-heather')
        checker_path = self.root / 'scripts/sandbox_check.py'
        checker, count = re.subn(b'HERO_BASE_COMMIT = "[a-f0-9]{40}"',
                                 b'HERO_BASE_COMMIT = "' + self.base.encode() + b'"', checker_path.read_bytes())
        self.assertEqual(count, 1)
        checker_path.write_bytes(checker)
        self.write('_includes/pages/home.html', TEMPLATE_REVIEWED)
        self.write('_data/hero.yml', DATA_REVIEWED)
        for name in MAINTENANCE[2:-1]:
            self.write(name, b'reviewed maintenance fixture\n')
        for lang, old, new in [('en', 'Photo by Joerg Metzner', 'Photos by Heather Eidson'),
                               ('es', 'Foto de Joerg Metzner', 'Fotos de Heather Eidson')]:
            path = self.root / f'_data/i18n/{lang}.yml'
            path.write_text(path.read_text().replace(old, new))
        self.write(CSS, b'.release-home .hero { color: navy; }\n')
        self.write(JS, b'/* reviewed slideshow fixture */\n')
        for name, data in PHOTO_BYTES.items():
            self.write(name, data)
        layout = self.root / '_layouts/default.html'
        layout.write_text(layout.read_text().replace(OLD_LINK, NEW_LINK).replace(OLD_BODY, NEW_BODY))
        self.write(MAINTENANCE[1], b'reviewed test fixture\n')
        self.write('scripts/tests/test_hero_slideshow.py', b'reviewed slideshow tests\n')
        for name in PAGES:
            p = self.root / name
            p.write_text(p.read_text().replace('[home.js]', '[home.js, hero-slideshow.js]'))
        fixture_inventory = {name: hashlib.sha256((self.root / name).read_bytes()).hexdigest()
                             for name in MAINTENANCE if name != 'scripts/sandbox_check.py'}
        manifest = {'reviewed-fixture': 'a' * 64}
        fixture_inventory['docs/help/reviewed-sources.json'] = hashlib.sha256(
            json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        digest = hashlib.sha256(json.dumps(fixture_inventory, sort_keys=True,
                                           separators=(',', ':')).encode()).hexdigest()
        checker, count = re.subn(b'HERO_MAINTENANCE_INVENTORY_SHA256 = "(?:UNREVIEWED|[a-f0-9]{64})"',
                                 f'HERO_MAINTENANCE_INVENTORY_SHA256 = "{digest}"'.encode(), checker_path.read_bytes())
        self.assertEqual(count, 1)
        checker_path.write_bytes(checker)
        manifest['scripts/sandbox_check.py'] = hashlib.sha256(checker_path.read_bytes()).hexdigest()
        self.write('docs/help/reviewed-sources.json', json.dumps(manifest).encode())
        self.git('add', '-A')
        self.git('commit', '-qm', 'preview')
        self.paths = [Path(self.tmp.name) / 'assets.json', Path(self.tmp.name) / 'maintenance.json']
        self.records = [self.record('homepage-hero-assets', [CSS, JS]), self.record('homepage-hero-maintenance', MAINTENANCE)]
        self.review_digest = hashlib.sha256(json.dumps(self.records[1]).encode()).hexdigest()

    def write(self, name, data):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.root), *args], check=True, capture_output=True, text=True).stdout

    def record(self, purpose, names):
        return {'version': 1, 'purpose': purpose, 'sandbox_id': 'homepage-hero-heather',
                **copy.deepcopy(SOURCE),
                'checkout': str(self.root.resolve()), 'base_commit': self.base,
                'head_commit': self.git('rev-parse', 'HEAD').strip(),
                'pages': PAGES, 'routes': ['/', '/es/'], 'scope': '.release-home',
                'files': [{'path': n, 'sha256': hashlib.sha256((self.root / n).read_bytes()).hexdigest()} for n in names]}

    def check(self, use=(True, True), write=True, extra=(), refresh_review=True, python_flags=()):
        cmd = [sys.executable, *python_flags, str(self.root / 'scripts/sandbox_check.py'), '--json', *extra]
        for yes, path, rec, flag in zip(use, self.paths, self.records, ['--homepage-hero-approval-file', '--homepage-hero-maintenance-approval-file']):
            if yes:
                if write:
                    path.write_text(json.dumps(rec))
                    path.chmod(0o600)
                cmd += [flag, str(path)]
        if use[1]:
            if refresh_review and write:
                self.review_digest = hashlib.sha256(json.dumps(self.records[1]).encode()).hexdigest()
            cmd += ['--homepage-hero-maintenance-review-sha256', self.review_digest]
        result = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(result.stderr, '')
        return result.returncode, json.loads(result.stdout)

    def test_exact_assets_and_separate_maintenance_records(self):
        self.assertEqual(self.check((False, False))[0], 1)
        self.assertEqual(self.check((True, False))[0], 1)
        self.assertEqual(self.check((False, True))[0], 1)
        code, report = self.check()
        self.assertEqual(code, 0, report)
        self.assertTrue(any('preview only' in note.lower() for note in report['notes']))

    def test_provenance_and_scope_fields_are_exact(self):
        for index in (0, 1):
            original = copy.deepcopy(self.records[index])
            for key, value in [('version', True), ('purpose', 'other'), ('sandbox_id', 'other'),
                               ('authorizer_id', 'U0CE2G08ZRC'), ('checkout', '/other'),
                               ('source', dict(original['source'], message_ts='wrong-approval')),
                               ('source', dict(original['source'], question_ts='wrong-question')),
                               ('base_commit', '0' * 40), ('head_commit', '0' * 40),
                               ('scope', '.other'), ('pages', ['index.html']), ('routes', ['/']),
                               ('files', []), ('extra', 1)]:
                self.records[index] = dict(original, **{key: value})
                with self.subTest(index=index, key=key):
                    self.assertEqual(self.check()[0], 1)
            self.records[index] = original

    def test_changed_asset_bytes_and_modes_block(self):
        for name in (CSS, JS):
            target = self.root / name
            data = target.read_bytes()
            target.write_bytes(data + b'\n/* changed */')
            self.assertEqual(self.check()[0], 1)
            target.write_bytes(data)
            target.chmod(0o755)
            self.assertEqual(self.check()[0], 1)
            target.chmod(0o644)
        self.assertEqual(self.check()[0], 0)

    def test_private_record_security(self):
        self.assertEqual(self.check()[0], 0)
        for mode in (0o400, 0o644, 0o700):
            self.paths[0].chmod(mode)
            self.assertEqual(self.check(write=False)[0], 1)
        self.paths[0].chmod(0o600)
        original = self.paths[0].with_suffix('.real')
        self.paths[0].rename(original)
        self.paths[0].symlink_to(original)
        self.assertEqual(self.check(write=False)[0], 1)
        self.paths[0].unlink()
        self.paths[0] = self.root / 'approval.json'
        self.assertEqual(self.check()[0], 1)

    def test_unrelated_existing_event_change_is_blocked(self):
        for flags in ((), ('-S',)):
            with self.subTest(flags=flags):
                baseline = self.git('rev-parse', 'HEAD').strip()
                code, report = self.check(python_flags=flags)
                self.assertEqual(code, 0, report)
                self.write('_data/event.yml', b'show: false\n')
                self.git('add', '_data/event.yml')
                self.git('commit', '-qm', 'unrelated event')
                for record in self.records:
                    record['head_commit'] = self.git('rev-parse', 'HEAD').strip()
                code, report = self.check(python_flags=flags)
                self.git('reset', '--hard', baseline)
                for record in self.records:
                    record['head_commit'] = baseline
                self.assertEqual(code, 1, report)
                self.assertTrue(any('_data/event.yml' in item for item in report['blocking']), report)

    def test_entire_inventory_blocks_extras_and_missing_required_paths(self):
        for flags in ((), ('-S',)):
            for attack in ('extra-page', 'deleted-event', 'missing-maintenance'):
                with self.subTest(flags=flags, attack=attack):
                    baseline = self.git('rev-parse', 'HEAD').strip()
                    if attack == 'extra-page':
                        name = 'unrelated.md'
                        self.write(name, b'---\nlayout: default\n---\nUnrelated\n')
                    elif attack == 'deleted-event':
                        name = '_data/event.yml'
                        (self.root / name).unlink()
                    else:
                        name = 'docs/help/team-help.md'
                        self.write(name, b'baseline\n')
                    self.git('add', '-A')
                    self.git('commit', '-qm', 'inventory attack')
                    for record in self.records:
                        record['head_commit'] = self.git('rev-parse', 'HEAD').strip()
                    code, report = self.check(python_flags=flags)
                    self.git('reset', '--hard', baseline)
                    for record in self.records:
                        record['head_commit'] = baseline
                    self.assertEqual(code, 1, report)
                    self.assertTrue(any('inventory mismatch' in item and name in item
                                        for item in report['blocking']), report)

    def test_merged_main_news_is_base_not_candidate_and_candidate_news_blocks(self):
        self.git('checkout', '-q', 'main')
        news = b'{"news": ["independently merged main"]}\n'
        self.write('data/news.json', news)
        self.git('add', 'data/news.json')
        self.git('commit', '-qm', 'independent main news')
        self.base = self.git('rev-parse', 'HEAD').strip()
        self.git('update-ref', 'refs/remotes/origin/main', self.base)
        self.git('checkout', '-q', 'sandbox/homepage-hero-heather')
        self.git('merge', '--no-edit', 'main')
        checker_path = self.root / 'scripts/sandbox_check.py'
        checker = re.sub(rb'HERO_BASE_COMMIT = "[a-f0-9]{40}"',
                         b'HERO_BASE_COMMIT = "' + self.base.encode() + b'"', checker_path.read_bytes())
        checker_path.write_bytes(checker)
        manifest_path = self.root / 'docs/help/reviewed-sources.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['scripts/sandbox_check.py'] = hashlib.sha256(checker).hexdigest()
        manifest_path.write_text(json.dumps(manifest))
        self.git('add', '-A')
        self.git('commit', '-qm', 'repin merged fixture')
        self.records = [self.record('homepage-hero-assets', [CSS, JS]),
                        self.record('homepage-hero-maintenance', MAINTENANCE)]
        self.assertEqual((self.root / 'data/news.json').read_bytes(), news)
        self.assertNotIn('data/news.json', self.git('diff', '--name-only', 'origin/main...HEAD').splitlines())
        for flags in ((), ('-S',)):
            code, report = self.check(python_flags=flags)
            self.assertEqual(code, 0, report)
        self.write('data/news.json', b'{"news": ["candidate tampering"]}\n')
        self.git('add', 'data/news.json')
        self.git('commit', '-qm', 'candidate news change')
        for record in self.records:
            record['head_commit'] = self.git('rev-parse', 'HEAD').strip()
        for flags in ((), ('-S',)):
            code, report = self.check(python_flags=flags)
            self.assertEqual(code, 1, report)
            self.assertTrue(any('inventory mismatch' in item and 'data/news.json' in item
                                for item in report['blocking']), report)

    def test_other_sandbox_and_unapproved_script_remain_blocked(self):
        self.git('checkout', '-qb', 'sandbox/other')
        self.assertEqual(self.check()[0], 1)
        self.git('checkout', '-q', 'sandbox/homepage-hero-heather')
        self.write('assets/js/evil.js', b'evil();')
        self.git('add', '-A')
        self.git('commit', '-qm', 'unapproved script')
        for record in self.records:
            record['head_commit'] = self.git('rev-parse', 'HEAD').strip()
        self.assertEqual(self.check()[0], 1)

    def test_unscoped_or_fetching_css_is_rejected_even_with_matching_digest(self):
        for css in (b'body { color: red; }', b'.release-home { background: url(https://evil.invalid/x); }'):
            self.write(CSS, css)
            self.git('add', CSS)
            self.git('commit', '-qm', 'unsafe css')
            for record in self.records:
                record['head_commit'] = self.git('rev-parse', 'HEAD').strip()
            self.records[0]['files'][0]['sha256'] = hashlib.sha256(css).hexdigest()
            self.assertEqual(self.check()[0], 1)


    def test_unreviewed_layout_change_cannot_expand_asset_routes(self):
        layout = self.root / '_layouts/default.html'
        layout.write_text(layout.read_text().replace("page.url == '/es/'", "page.url == '/other/'"))
        self.git('add', '-A')
        self.git('commit', '-qm', 'route tampering')
        for record in self.records:
            record['head_commit'] = self.git('rev-parse', 'HEAD').strip()
        self.assertEqual(self.check()[0], 1)


    def test_legacy_css_record_cannot_bypass_hero_hash_approval(self):
        legacy = Path(self.tmp.name) / 'legacy.json'
        legacy.write_text(json.dumps({'version': 1, 'purpose': 'sandbox-review',
            'sandbox_id': 'homepage-hero-heather', 'authorizer_id': 'U0CE4NY7KC2',
            'source': {'channel_id': 'C0CEMKENSQ1', 'message_ts': '100.000000'},
            'css': [{'path': CSS, 'routes': ['/', '/es/'], 'scope': '.release-home'}], 'workbooks': []}))
        legacy.chmod(0o600)
        code, report = self.check((False, True), extra=['--approval-file', str(legacy)])
        self.assertEqual(code, 1)
        self.assertTrue(any('Invalid scoped approval' in item for item in report['blocking']), report)

    def test_duplicate_fields_symlink_parents_wrong_owner_and_url(self):
        self.assertEqual(self.check()[0], 0)
        text = self.paths[0].read_text()
        self.paths[0].write_text(text.replace('"version": 1', '"version": 1, "version": 1'))
        self.assertEqual(self.check(write=False)[0], 1)
        self.paths[0].write_text(text)
        spec = importlib.util.spec_from_file_location('hero_checker', self.root / 'scripts/sandbox_check.py')
        assert spec is not None and spec.loader is not None
        checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checker)
        with patch.object(checker.os, 'getuid', return_value=os.getuid() + 1):
            with self.assertRaisesRegex(ValueError, 'operator-owned'):
                checker.load_homepage_hero_approval(self.paths[0], 'homepage-hero-assets', 'origin/main', None)
        for url in ('http://forabrighterevanston.org/sandbox/homepage-hero-heather/',
                    'https://evil.invalid/sandbox/homepage-hero-heather/',
                    'https://forabrighterevanston.org/sandbox/other/',
                    'https://forabrighterevanston.org/sandbox/homepage-hero-heather/?x=1'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                checker.load_homepage_hero_approval(self.paths[0], 'homepage-hero-assets', 'origin/main', url)
        linkdir = Path(self.tmp.name) / 'symlinked'
        linkdir.symlink_to(self.paths[0].parent, target_is_directory=True)
        with self.assertRaises(ValueError):
            checker.load_homepage_hero_approval(linkdir / self.paths[0].name, 'homepage-hero-assets', 'origin/main', None)

    def test_staged_worktree_tampering_and_foreign_page_loader_block(self):
        page = self.root / PAGES[0]
        page.write_text(page.read_text().replace('hero-slideshow.js', 'other.js'))
        self.git('add', PAGES[0])
        self.assertEqual(self.check()[0], 1)
        self.git('commit', '-qm', 'replace loader')
        for record in self.records:
            record['head_commit'] = self.git('rev-parse', 'HEAD').strip()
        self.assertEqual(self.check()[0], 1)


    def test_changed_committed_assets_cannot_be_reapproved_by_new_record_hash(self):
        for index, name in enumerate((CSS, JS)):
            with self.subTest(name=name):
                baseline = self.git('rev-parse', 'HEAD').strip()
                path = self.root / name
                path.write_bytes(path.read_bytes() + b'\n/* changed */\n')
                self.git('add', name)
                self.git('commit', '-qm', 'different asset')
                for record in self.records:
                    record['head_commit'] = self.git('rev-parse', 'HEAD').strip()
                self.records[0]['files'][index]['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
                code = self.check()[0]
                self.git('reset', '--hard', baseline)
                self.records = [self.record('homepage-hero-assets', [CSS, JS]),
                                self.record('homepage-hero-maintenance', MAINTENANCE)]
                self.assertEqual(code, 1)

    def test_unreviewed_homepage_body_and_tracking_image_are_rejected(self):
        for name in PAGES:
            for payload in ('<p>Unreviewed copy</p>', '<img src="https://evil.invalid/tracker">'):
                for flags in ((), ('-S',)):
                    with self.subTest(page=name, payload=payload, flags=flags):
                        baseline = self.git('rev-parse', 'HEAD').strip()
                        self.assertEqual(self.check(python_flags=flags)[0], 0)
                        page = self.root / name
                        page.write_text(page.read_text() + payload + '\n')
                        self.git('add', name)
                        self.git('commit', '-qm', 'unreviewed homepage content')
                        for record in self.records:
                            record['head_commit'] = self.git('rev-parse', 'HEAD').strip()
                        code, report = self.check(python_flags=flags)
                        self.git('reset', '--hard', baseline)
                        for record in self.records:
                            record['head_commit'] = baseline
                        self.assertEqual(code, 1, report)
                        self.assertTrue(any('homepage' in x.lower() for x in report['blocking']), report)

    def test_unreviewed_homepage_translation_is_rejected(self):
        for lang in ('en', 'es'):
            for flags in ((), ('-S',)):
                with self.subTest(lang=lang, flags=flags):
                    baseline = self.git('rev-parse', 'HEAD').strip()
                    code, report = self.check(python_flags=flags)
                    self.assertEqual(code, 0, report)
                    path = self.root / f'_data/i18n/{lang}.yml'
                    path.write_text(path.read_text().replace('headline: Original', 'headline: Unreviewed'))
                    self.git('add', '-A')
                    self.git('commit', '-qm', 'unreviewed translation')
                    for record in self.records:
                        record['head_commit'] = self.git('rev-parse', 'HEAD').strip()
                    code, report = self.check(python_flags=flags)
                    self.git('reset', '--hard', baseline)
                    for record in self.records:
                        record['head_commit'] = baseline
                    self.assertEqual(code, 1, report)
                    self.assertTrue(any('homepage' in x.lower() for x in report['blocking']), report)

    def test_photo_tamper_substitution_extra_and_mode_rejected(self):
        for flags in ((), ('-S',)):
            for attack in ('tamper', 'substitute', 'extra', 'extra_pdf', 'mode'):
                with self.subTest(flags=flags, attack=attack):
                    baseline = self.git('rev-parse', 'HEAD').strip()
                    code, report = self.check(python_flags=flags)
                    self.assertEqual(code, 0, report)
                    name = PHOTO_NAMES[0]
                    if attack == 'tamper':
                        self.write(name, PHOTO_BYTES[name] + b'tampered')
                    elif attack == 'substitute':
                        self.write(name, PHOTO_BYTES[PHOTO_NAMES[1]])
                    elif attack == 'extra':
                        self.write('assets/img/hero/unapproved.jpg', b'extra')
                    elif attack == 'extra_pdf':
                        self.write('assets/files/unapproved.pdf', b'extra')
                    else:
                        (self.root / name).chmod(0o755)
                    self.git('add', '-A')
                    self.git('commit', '-qm', 'unreviewed photo')
                    for record in self.records:
                        record['head_commit'] = self.git('rev-parse', 'HEAD').strip()
                    code, report = self.check(python_flags=flags)
                    self.git('reset', '--hard', baseline)
                    for record in self.records:
                        record['head_commit'] = baseline
                    self.assertEqual(code, 1, report)
                    self.assertTrue(any('photo' in x.lower() or 'image' in x.lower() for x in report['blocking']), report)

    def test_ignored_extra_media_cannot_bypass_inventory(self):
        for flags in ((), ('-S',)):
            with self.subTest(flags=flags):
                code, report = self.check(python_flags=flags)
                self.assertEqual(code, 0, report)
                exclude = self.root / '.git/info/exclude'
                exclude.write_text(exclude.read_text() + '\nassets/img/hero/ignored.jpg\n')
                self.write('assets/img/hero/ignored.jpg', b'ignored media')
                code, report = self.check(python_flags=flags)
                (self.root / 'assets/img/hero/ignored.jpg').unlink()
                self.assertEqual(code, 1, report)
                self.assertTrue(any('media' in x.lower() for x in report['blocking']), report)

    def test_repin_cannot_authorize_unsafe_individual_photo_records(self):
        cases = [DATA_REVIEWED.replace(b'heather-eidson-meetup-01.jpg', b'https://evil.invalid/x.jpg', 1),
                 DATA_REVIEWED.replace(b'heather-eidson-meetup-01.jpg', b'heather-eidson-meetup-02.jpg', 1),
                 DATA_REVIEWED.replace(b'width: 1600', b'width: 0', 1),
                 DATA_REVIEWED.replace(b'50% 50%', b'05% 075%', 1),
                 DATA_REVIEWED.replace(b'50% 50%', b'00% 100%', 1),
                 DATA_REVIEWED.replace(b'50% 50%', b'0% 010%', 1),
                 DATA_REVIEWED.replace(b'50% 50%', b'101% 50%', 1),
                 DATA_REVIEWED.replace(b'50% 50%', b'-1% 50%', 1),
                 DATA_REVIEWED.replace(b'50% 50%', b'50.0% 50%', 1),
                 DATA_REVIEWED.replace(b'50% 50%', b'50%  50%', 1)]
        for flags in ((), ('-S',)):
            for data in cases:
                with self.subTest(flags=flags, data=data[:80]):
                    baseline = self.git('rev-parse', 'HEAD').strip()
                    self.write('_data/hero.yml', data)
                    checker_path = self.root / 'scripts/sandbox_check.py'
                    checker = checker_path.read_bytes()
                    checker = re.sub(rb'HERO_DATA_SHA256 = "[a-f0-9]{64}"',
                                     b'HERO_DATA_SHA256 = "' + hashlib.sha256(data).hexdigest().encode() + b'"', checker)
                    checker_path.write_bytes(checker)
                    manifest_path = self.root / 'docs/help/reviewed-sources.json'
                    manifest = json.loads(manifest_path.read_text())
                    manifest['scripts/sandbox_check.py'] = hashlib.sha256(checker).hexdigest()
                    manifest_path.write_text(json.dumps(manifest))
                    self.git('add', '-A')
                    self.git('commit', '-qm', 'repin unsafe record')
                    for record in self.records:
                        record['head_commit'] = self.git('rev-parse', 'HEAD').strip()
                    for item in self.records[1]['files']:
                        item['sha256'] = hashlib.sha256((self.root / item['path']).read_bytes()).hexdigest()
                    code, report = self.check(python_flags=flags)
                    self.git('reset', '--hard', baseline)
                    self.records = [self.record('homepage-hero-assets', [CSS, JS]),
                                    self.record('homepage-hero-maintenance', MAINTENANCE)]
                    self.assertEqual(code, 1, report)
                    self.assertTrue(any('photo record' in x.lower() for x in report['blocking']), report)

    def test_canonical_focal_boundaries_match_css_and_are_accepted(self):
        css = (CHECKER.parent.parent / CSS).read_text()
        for axis in ('x', 'y'):
            values = re.findall(r'data-hero-position-' + axis + r'=\"([0-9]+%)\"', css)
            self.assertEqual(set(values), {f'{value}%' for value in range(101)})
            self.assertEqual(len(values), 101)
        for flags in ((), ('-S',)):
            for position in (b'0% 100%', b'99% 1%'):
                with self.subTest(flags=flags, position=position):
                    baseline = self.git('rev-parse', 'HEAD').strip()
                    data = DATA_REVIEWED.replace(b'50% 50%', position, 1)
                    self.write('_data/hero.yml', data)
                    checker_path = self.root / 'scripts/sandbox_check.py'
                    checker = re.sub(rb'HERO_DATA_SHA256 = "[a-f0-9]{64}"',
                                     b'HERO_DATA_SHA256 = "' + hashlib.sha256(data).hexdigest().encode() + b'"',
                                     checker_path.read_bytes())
                    checker_path.write_bytes(checker)
                    manifest_path = self.root / 'docs/help/reviewed-sources.json'
                    manifest = json.loads(manifest_path.read_text())
                    manifest['scripts/sandbox_check.py'] = hashlib.sha256(checker).hexdigest()
                    manifest_path.write_text(json.dumps(manifest))
                    self.git('add', '-A')
                    self.git('commit', '-qm', 'canonical position fixture')
                    self.records = [self.record('homepage-hero-assets', [CSS, JS]),
                                    self.record('homepage-hero-maintenance', MAINTENANCE)]
                    code, report = self.check(python_flags=flags)
                    self.git('reset', '--hard', baseline)
                    self.records = [self.record('homepage-hero-assets', [CSS, JS]),
                                    self.record('homepage-hero-maintenance', MAINTENANCE)]
                    self.assertEqual(code, 0, report)

    def test_template_substitutions_cannot_ride_on_asset_approval(self):
        for html in (b'<img src="https://evil.invalid/tracker">',
                     b'<picture><source srcset="//evil.invalid/tracker"></picture>',
                     b'<p>Unreviewed copy</p>'):
            with self.subTest(html=html):
                self.write('_includes/pages/home.html', html)
                self.git('add', '-A')
                self.git('commit', '-qm', 'unreviewed template')
                for record in self.records:
                    record['head_commit'] = self.git('rev-parse', 'HEAD').strip()
                code, report = self.check()
                self.assertEqual(code, 1, report)
                self.assertTrue(any('hero input must match independently reviewed exact bytes' in x
                                    for x in report['blocking']), report)

    def test_maintenance_record_cannot_reapprove_changed_committed_bytes(self):
        name = 'docs/help/team-help.md'
        self.write(name, b'unreviewed but committed\n')
        self.git('add', name)
        self.git('commit', '-qm', 'unreviewed maintenance')
        for record in self.records:
            record['head_commit'] = self.git('rev-parse', 'HEAD').strip()
        for entry in self.records[1]['files']:
            if entry['path'] == name:
                entry['sha256'] = hashlib.sha256((self.root / name).read_bytes()).hexdigest()
        code, report = self.check(refresh_review=False)
        self.assertEqual(code, 1, report)
        self.assertTrue(any('independently reviewed record SHA-256' in x for x in report['blocking']), report)

    def test_fresh_caller_digest_cannot_replace_independent_maintenance_pin(self):
        name = 'docs/help/team-help.md'
        self.write(name, b'unreviewed but committed\n')
        self.git('add', name)
        self.git('commit', '-qm', 'unreviewed maintenance')
        for record in self.records:
            record['head_commit'] = self.git('rev-parse', 'HEAD').strip()
        for entry in self.records[1]['files']:
            if entry['path'] == name:
                entry['sha256'] = hashlib.sha256((self.root / name).read_bytes()).hexdigest()
        code, report = self.check(refresh_review=True)
        self.assertEqual(code, 1, report)
        self.assertTrue(any('independently pinned maintenance inventory' in x for x in report['blocking']), report)

    def test_tampered_reviewed_sources_manifest_is_not_reapproved(self):
        name = 'docs/help/reviewed-sources.json'
        manifest = json.loads((self.root / name).read_text())
        manifest['other-reviewed-file'] = '0' * 64
        self.write(name, json.dumps(manifest).encode())
        self.git('add', name)
        self.git('commit', '-qm', 'tampered manifest')
        for record in self.records:
            record['head_commit'] = self.git('rev-parse', 'HEAD').strip()
        for entry in self.records[1]['files']:
            if entry['path'] == name:
                entry['sha256'] = hashlib.sha256((self.root / name).read_bytes()).hexdigest()
        code, report = self.check(refresh_review=True)
        self.assertEqual(code, 1, report)
        self.assertTrue(any('independently pinned maintenance inventory' in x for x in report['blocking']), report)

    def test_stdlib_only_loads_existing_and_new_script_lists(self):
        cmd = [sys.executable, '-S', '-c',
               "import runpy,sys; c=runpy.run_path(sys.argv[1]); "
               "print(c['parse_front_matter']('scripts: [home.js, hero-slideshow.js]')['scripts'])",
               str(self.root / 'scripts/sandbox_check.py')]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout.strip(), "['home.js', 'hero-slideshow.js']")
        code, report = self.check(python_flags=('-S',))
        self.assertEqual(code, 0, report)

    def test_unreviewed_hero_data_cannot_be_reapproved(self):
        self.write('_data/hero.yml', b'- file: \'" onerror="alert(1)\'\n')
        self.git('add', '-A')
        self.git('commit', '-qm', 'unreviewed hero data')
        for record in self.records:
            record['head_commit'] = self.git('rev-parse', 'HEAD').strip()
        code, report = self.check()
        self.assertEqual(code, 1, report)
        self.assertTrue(any('_data/hero.yml: hero input must match' in x for x in report['blocking']), report)

    def test_review_digest_must_be_independent_and_present(self):
        self.check()
        for digest in ('', '0' * 64, self.review_digest.upper()):
            self.review_digest = digest
            code, report = self.check(write=False, refresh_review=False)
            self.assertEqual(code, 1, report)
            self.assertTrue(any('independently reviewed record SHA-256' in x for x in report['blocking']), report)

    def test_production_base_and_template_baseline_are_pinned(self):
        spec = importlib.util.spec_from_file_location('production_base_checker', CHECKER)
        assert spec is not None and spec.loader is not None
        checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checker)
        self.assertEqual(checker.HERO_BASE_COMMIT, '0d6f0373fba5c5629bafa8423d855e68931e03e3')
        self.assertEqual(checker.HERO_TEMPLATE_BASE_SHA256,
                         'f74d592ded8bfa7196061e8044040c86171f7d65118a145ea794d1212657c762')

    def test_original_provenance_is_pinned_to_real_source(self):
        spec = importlib.util.spec_from_file_location('production_checker', CHECKER)
        assert spec is not None and spec.loader is not None
        checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checker)
        source = {'authorizer_id': 'U0CE4NY7KC2', 'source': {'channel_id': 'C0CEMKENSQ1',
                  'message_ts': '1794802992.360449', 'question_ts': '1794800455.768529'}}
        digest = hashlib.sha256(json.dumps(source, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        self.assertEqual(checker.HERO_SOURCE_SHA256, digest)

    def test_advanced_main_is_rejected_even_if_record_is_refreshed(self):
        self.git('checkout', '-q', 'main')
        self.write('new-main.txt', b'advance\n')
        self.git('add', '-A')
        self.git('commit', '-qm', 'main advanced')
        newer = self.git('rev-parse', 'HEAD').strip()
        self.git('update-ref', 'refs/remotes/origin/main', newer)
        self.git('checkout', '-q', 'sandbox/homepage-hero-heather')
        for record in self.records:
            record['base_commit'] = newer
        code, report = self.check()
        self.assertEqual(code, 1, report)
        self.assertTrue(any('current base, HEAD and merge base' in x for x in report['blocking']), report)


if __name__ == '__main__':
    unittest.main()
