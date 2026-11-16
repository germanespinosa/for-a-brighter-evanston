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
PUBLICATION_SOURCE = {'authorizer_id': 'PUBLISHER_FIXTURE', 'source': {
    'channel_id': 'PUBLICATION_CHANNEL_FIXTURE', 'question_ts': 'publication-question-fixture',
    'message_ts': 'publication-answer-fixture', 'answer': 'yes'}}
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
            b'HERO_PUBLICATION_SOURCE_SHA256 = ': json.dumps(PUBLICATION_SOURCE, sort_keys=True, separators=(',', ':')).encode(),
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
        checker, count = re.subn(b'HERO_AUTHORIZATION_HEAD = "[a-f0-9]{40}"',
                                 b'HERO_AUTHORIZATION_HEAD = "' + self.base.encode() + b'"', checker)
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

    def publication_record(self):
        return {'version': 1, 'purpose': 'homepage-hero-publication-safeguards',
                'sandbox_id': 'homepage-hero-heather', **copy.deepcopy(PUBLICATION_SOURCE),
                'authorization_head': self.base,
                'checkout': str(self.root.resolve()), 'base_commit': self.base,
                'head_commit': self.git('rev-parse', 'HEAD').strip(),
                'pages': PAGES, 'routes': ['/', '/es/'], 'scope': '.release-home',
                'files': copy.deepcopy(self.records[1]['files'])}

    def check_publication(self, record, digest=None, use=(True, True), python_flags=()):
        path = Path(self.tmp.name) / 'publication.json'
        raw = json.dumps(record).encode()
        path.write_bytes(raw)
        path.chmod(0o600)
        if digest is None:
            digest = hashlib.sha256(raw).hexdigest()
        return self.check(use=use, extra=['--homepage-hero-publication-approval-file', str(path),
                                         '--homepage-hero-publication-review-sha256', digest], python_flags=python_flags)

    def test_distinct_reviewed_publication_safeguards_allow_review_not_publication(self):
        code, report = self.check_publication(self.publication_record())
        self.assertEqual(code, 0, report)
        self.assertTrue(any('normal team review and vote' in note.lower() for note in report['notes']), report)
        self.assertFalse(any('preview only; vote and publication are held' in note.lower() for note in report['notes']))

    def test_publication_record_rejects_wrong_provenance_scope_and_missing_previews(self):
        original = self.publication_record()
        for key, value in [('version', True), ('purpose', 'homepage-hero-maintenance'),
                           ('sandbox_id', 'other'), ('authorizer_id', 'other'),
                           ('source', dict(original['source'], channel_id='other')),
                           ('source', dict(original['source'], question_ts='other')),
                           ('source', dict(original['source'], message_ts='other')),
                           ('source', dict(original['source'], answer='no')),
                           ('authorization_head', '0' * 40), ('checkout', '/other'),
                           ('base_commit', '0' * 40), ('head_commit', '0' * 40),
                           ('scope', '.other'), ('pages', ['index.html']), ('routes', ['/']),
                           ('files', []), ('extra', 1)]:
            with self.subTest(key=key, value=value):
                self.assertEqual(self.check_publication(dict(original, **{key: value}))[0], 1)
        for use in ((False, False), (False, True), (True, False)):
            self.assertEqual(self.check_publication(original, use=use)[0], 1)
        self.assertEqual(self.check_publication(original, digest='0' * 64)[0], 1)
        self.assertEqual(self.check_publication(original, digest='')[0], 1)

    def test_publication_source_pin_and_scope_fail_closed_without_site_packages(self):
        original = self.publication_record()
        for flags in ((), ('-S',)):
            with self.subTest(flags=flags, attack='valid'):
                code, report = self.check_publication(original, python_flags=flags)
                self.assertEqual(code, 0, report)
            for key, value in (
                ('authorizer_id', 'OTHER_FIXTURE'),
                ('source', dict(original['source'], channel_id='OTHER_CHANNEL_FIXTURE')),
                ('source', dict(original['source'], question_ts='other-question')),
                ('source', dict(original['source'], message_ts='other-answer')),
                ('source', dict(original['source'], answer='no')),
                ('source', dict(original['source'], extra='unreviewed')),
                ('source', {k: v for k, v in original['source'].items() if k != 'question_ts'}),
                ('scope', '.other'), ('routes', ['/', '/es/', '/other/']),
                ('pages', ['index.html', 'es/index.html', 'other/index.html']),
            ):
                with self.subTest(flags=flags, key=key, value=value):
                    code, report = self.check_publication(dict(original, **{key: value}), python_flags=flags)
                    self.assertEqual(code, 1, report)
                    self.assertTrue(any('publication record schema, provenance or binding mismatch' in item
                                        for item in report['blocking']), report)

    def test_publication_authorization_head_must_be_an_ancestor(self):
        tree = self.git('rev-parse', 'HEAD^{tree}').strip()
        disconnected = self.git('commit-tree', tree, '-m', 'unrelated authorization').strip()
        checker = self.root / 'scripts/sandbox_check.py'
        text = checker.read_text()
        needle = f'HERO_AUTHORIZATION_HEAD = "{self.base}"'
        self.assertIn(needle, text)
        checker.write_text(text.replace(needle, f'HERO_AUTHORIZATION_HEAD = "{disconnected}"'))
        manifest_path = self.root / 'docs/help/reviewed-sources.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['scripts/sandbox_check.py'] = hashlib.sha256(checker.read_bytes()).hexdigest()
        manifest_path.write_text(json.dumps(manifest))
        self.git('add', '-A')
        self.git('commit', '-qm', 'disconnected authorization fixture')
        self.records = [self.record('homepage-hero-assets', [CSS, JS]),
                        self.record('homepage-hero-maintenance', MAINTENANCE)]
        record = self.publication_record()
        record['authorization_head'] = disconnected
        code, report = self.check_publication(record)
        self.assertEqual(code, 1, report)
        self.assertTrue(any('authorization' in item.lower() for item in report['blocking']), report)

    def test_publication_record_permissions_stale_heads_and_duplicate_fields(self):
        record = self.publication_record()
        self.assertEqual(self.check_publication(record)[0], 0)
        path = Path(self.tmp.name) / 'publication.json'
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        args = ['--homepage-hero-publication-approval-file', str(path),
                '--homepage-hero-publication-review-sha256', digest]
        for mode in (0o400, 0o644, 0o700):
            path.chmod(mode)
            self.assertEqual(self.check(extra=args)[0], 1)
        path.chmod(0o600)
        actual = path.with_suffix('.real')
        path.rename(actual)
        path.symlink_to(actual)
        self.assertEqual(self.check(extra=args)[0], 1)
        path.unlink()
        actual.rename(path)
        duplicate = raw.replace(b'"version": 1', b'"version": 1, "version": 1', 1)
        path.write_bytes(duplicate)
        args[-1] = hashlib.sha256(duplicate).hexdigest()
        self.assertEqual(self.check(extra=args)[0], 1)
        path.write_bytes(raw)
        args[-1] = digest
        self.git('commit', '--allow-empty', '-qm', 'new candidate')
        self.assertEqual(self.check(extra=args)[0], 1)

    def test_hero_publication_hook_and_manual_fail_closed(self):
        manual = (CHECKER.parent.parent / 'docs/agents/fabian-website.md').read_text()
        match = re.search(r'<!-- hero-pre-push-hook -->\n```sh\n(.*?)```', manual, re.S)
        self.assertIsNotNone(match, 'hero publication must provide the actual reviewed hook')
        hook = Path(self.tmp.name) / 'pre-push'
        hook.write_text(match.group(1))
        hook.chmod(0o700)
        base = self.base
        voted = self.git('rev-parse', 'HEAD').strip()
        env = dict(os.environ, FABIAN_EXPECTED_MAIN=base, FABIAN_EXPECTED_MERGE=voted)
        def run(lines):
            return subprocess.run([str(hook), 'origin', 'fixture'], input=lines, text=True,
                                  capture_output=True, env=env).returncode
        valid = f'HEAD {voted} refs/heads/main {base}\n'
        self.assertEqual(run(valid), 0)
        for invalid in ('', valid + valid, f'HEAD {voted} refs/heads/other {base}\n',
                        f'HEAD {voted} refs/heads/main {"0" * 40}\n',
                        f'HEAD {"0" * 40} refs/heads/main {base}\n'):
            with self.subTest(input=invalid):
                self.assertNotEqual(run(invalid), 0)
        for phrase in ('2 yes / 0 no', 'no code action', 'entire merge tree',
                       'no retries', 'cooperating handlers', 'live bytes',
                       'cancellation cutoff', 'not atomic', 'eligible cancellation'):
            self.assertIn(phrase, manual.lower())

    def test_preflight_switches_to_expected_merge_after_publication_push(self):
        manual = (CHECKER.parent.parent / 'docs/agents/fabian-website.md').read_text().lower()
        marker = 'immediately before **each pre-push external action**'
        self.assertIn(marker, manual)
        preflight = manual.split(marker, 1)[1].split('after independent review, help regeneration', 1)[0]
        self.assertIn('through initiating the main push', preflight)
        self.assertIn('after the main push', preflight)
        self.assertIn('expected merge oid', preflight)
        self.assertNotIn('repeat immediately before each subsequent external action', preflight)

    def test_hero_closeout_requires_all_verification_before_cleanup_or_success(self):
        manual = (CHECKER.parent.parent / 'docs/agents/fabian-website.md').read_text().lower()
        self.assertIn('<!-- hero-closeout-gate -->', manual)
        self.assertIn('<!-- end-hero-closeout-gate -->', manual)
        closeout = manual.split('<!-- hero-closeout-gate -->', 1)[1].split('<!-- end-hero-closeout-gate -->', 1)[0]
        for requirement in ('production build/deploy', 'actual remote main', 'live bytes',
                            'all ten photo', 'both home routes', 'unrelated route',
                            'news', 'sitemap', 'claim ownership', 'stop',
                            'do not delete', 'do not post', 'do not switch', 'unverified'):
            with self.subTest(requirement=requirement):
                self.assertIn(requirement, closeout)
        steps = manual.split('**when the vote passes:**', 1)[1].split('## 10.', 1)[0]
        self.assertIn('only after the hero-closeout gate', steps)
        cards = (CHECKER.parent.parent / 'docs/agents/fabian-website-cards.md').read_text().lower()
        card = cards.split('## card g:', 1)[1].split('## card', 1)[0]
        self.assertIn('only after the hero-closeout gate', card)
        self.assertIn('stop', card)

    def test_documented_hero_claim_is_exclusive_for_same_vote(self):
        manual = (CHECKER.parent.parent / 'docs/agents/fabian-website.md').read_text()
        match = re.search(r'<!-- hero-claim-command -->\n```sh\n(.*?)```', manual, re.S)
        self.assertIsNotNone(match, 'hero must document atomic local per-vote acquisition')
        assert match is not None
        claim = Path(self.tmp.name) / 'vote-claim'
        env = dict(os.environ, claim=str(claim))
        def acquire():
            return subprocess.run(['sh', '-eu', '-c', match.group(1)], env=env,
                                  capture_output=True, text=True)
        self.assertEqual(acquire().returncode, 0)
        self.assertTrue(claim.is_dir())
        self.assertNotEqual(acquire().returncode, 0)
        self.assertTrue(claim.is_dir())

    def test_documented_hero_cleanup_uses_exact_vote_lease(self):
        manual = (CHECKER.parent.parent / 'docs/agents/fabian-website.md').read_text()
        match = re.search(r'<!-- hero-cleanup-command -->\n```sh\n(.*?)```', manual, re.S)
        self.assertIsNotNone(match, 'hero cleanup must provide an executable exact-lease command')
        folder = Path(self.tmp.name)
        remote, repo = folder / 'cleanup-remote.git', folder / 'cleanup-repo'
        subprocess.run(['git', 'init', '--bare', '-q', str(remote)], check=True)
        subprocess.run(['git', 'init', '-q', '-b', 'main', str(repo)], check=True)
        def run(*args, check=True):
            return subprocess.run(['git', '-C', str(repo), *args], check=check,
                                  capture_output=True, text=True)
        run('config', 'user.email', 'test@example.test')
        run('config', 'user.name', 'Test')
        run('remote', 'add', 'origin', str(remote))
        run('commit', '--allow-empty', '-qm', 'voted')
        voted = run('rev-parse', 'HEAD').stdout.strip()
        ref = 'refs/heads/sandbox/homepage-hero-heather'
        run('push', '-q', 'origin', f'HEAD:{ref}')
        run('commit', '--allow-empty', '-qm', 'newer')
        newer = run('rev-parse', 'HEAD').stdout.strip()
        run('push', '-q', 'origin', f'HEAD:{ref}')
        env = dict(os.environ, voted_sha=voted)
        def cleanup():
            return subprocess.run(['sh', '-eu', '-c', match.group(1)], cwd=repo, env=env,
                                  capture_output=True, text=True)
        self.assertNotEqual(cleanup().returncode, 0)
        self.assertEqual(run('ls-remote', 'origin', ref).stdout.split()[0], newer)
        run('push', '-q', '--force', 'origin', f'{voted}:{ref}')
        self.assertEqual(cleanup().returncode, 0)
        self.assertEqual(run('ls-remote', 'origin', ref).stdout, '')
        self.assertNotEqual(cleanup().returncode, 0, 'a missing ref is not a fresh successful deletion')

    def test_documented_hook_guards_actual_git_push_and_server_race(self):
        manual = (CHECKER.parent.parent / 'docs/agents/fabian-website.md').read_text()
        match = re.search(r'<!-- hero-pre-push-hook -->\n```sh\n(.*?)```', manual, re.S)
        assert match is not None
        folder = Path(self.tmp.name)
        remote, repo, hooks = folder / 'remote.git', folder / 'push-repo', folder / 'hooks'
        subprocess.run(['git', 'init', '--bare', '-q', str(remote)], check=True)
        subprocess.run(['git', 'init', '-q', '-b', 'main', str(repo)], check=True)
        def run(*args, env=None, check=True):
            return subprocess.run(['git', '-C', str(repo), *args], check=check,
                                  capture_output=True, text=True, env=env)
        run('config', 'user.email', 'test@example.test')
        run('config', 'user.name', 'Test')
        run('remote', 'add', 'origin', str(remote))
        run('commit', '--allow-empty', '-qm', 'base')
        base = run('rev-parse', 'HEAD').stdout.strip()
        run('push', '-q', 'origin', 'HEAD:refs/heads/main')
        run('commit', '--allow-empty', '-qm', 'intermediate')
        intermediate = run('rev-parse', 'HEAD').stdout.strip()
        run('push', '-q', 'origin', 'HEAD:refs/heads/main')
        run('commit', '--allow-empty', '-qm', 'candidate')
        candidate = run('rev-parse', 'HEAD').stdout.strip()
        hooks.mkdir()
        hook = hooks / 'pre-push'
        hook.write_text(match.group(1))
        hook.chmod(0o700)
        env = dict(os.environ, FABIAN_EXPECTED_MAIN=base, FABIAN_EXPECTED_MERGE=candidate)
        push = ('-c', f'core.hooksPath={hooks}', 'push', 'origin', 'HEAD:refs/heads/main')
        # The advanced server tip is still an ancestor, so ordinary push would succeed.
        self.assertEqual(run('push', '--dry-run', 'origin', 'HEAD:refs/heads/main').returncode, 0)
        self.assertNotEqual(run(*push, env=env, check=False).returncode, 0)
        def server(*args):
            return subprocess.run(['git', '--git-dir', str(remote), *args], check=True,
                                  capture_output=True, text=True).stdout.strip()
        self.assertEqual(server('rev-parse', 'refs/heads/main'), intermediate)
        server('update-ref', 'refs/heads/main', base)
        # Pre-receive advances the ref after advertisement but before the update.
        race_hook = remote / 'hooks/pre-receive'
        race_hook.write_text(f'#!/bin/sh\nunset GIT_QUARANTINE_PATH GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES\ngit update-ref refs/heads/main {intermediate} {base}\n')
        race_hook.chmod(0o700)
        race_result = run(*push, env=env, check=False)
        self.assertNotEqual(race_result.returncode, 0)
        self.assertEqual(server('rev-parse', 'refs/heads/main'), intermediate, race_result.stderr)
        race_hook.unlink()
        server('update-ref', 'refs/heads/main', base)
        self.assertEqual(run(*push, env=env, check=False).returncode, 0)
        self.assertEqual(server('rev-parse', 'refs/heads/main'), candidate)

    def test_exact_assets_and_separate_maintenance_records(self):
        self.assertEqual(self.check((False, False))[0], 1)
        self.assertEqual(self.check((True, False))[0], 1)
        self.assertEqual(self.check((False, True))[0], 1)
        code, report = self.check()
        self.assertEqual(code, 0, report)
        self.assertTrue(any('preview only' in note.lower() for note in report['notes']))

    def test_text_result_is_preview_only_for_eligible_hero(self):
        code, report = self.check()
        self.assertEqual(code, 0, report)
        result = subprocess.run([
            sys.executable, str(self.root / 'scripts/sandbox_check.py'),
            '--homepage-hero-approval-file', str(self.paths[0]),
            '--homepage-hero-maintenance-approval-file', str(self.paths[1]),
            '--homepage-hero-maintenance-review-sha256', self.review_digest,
        ], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('RESULT: OK FOR PREVIEW ONLY (vote/publication held)', result.stdout)
        self.assertNotIn('OK TO VOTE', result.stdout)

    def test_text_result_retains_vote_readiness_for_ordinary_candidate(self):
        self.git('checkout', '-qb', 'sandbox/ordinary', 'main')
        result = subprocess.run([sys.executable, str(self.root / 'scripts/sandbox_check.py')],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('RESULT: OK TO VOTE (review warnings)', result.stdout)

    def test_text_result_blocks_invalid_hero(self):
        result = subprocess.run([sys.executable, str(self.root / 'scripts/sandbox_check.py')],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('RESULT: NOT READY FOR A VOTE', result.stdout)
        self.assertNotIn('OK FOR PREVIEW ONLY', result.stdout)
        self.assertNotIn('OK TO VOTE', result.stdout)

    def test_provenance_and_scope_fields_are_exact(self):
        for index in (0, 1):
            original = copy.deepcopy(self.records[index])
            for key, value in [('version', True), ('purpose', 'other'), ('sandbox_id', 'other'),
                               ('authorizer_id', 'OTHER_FIXTURE'), ('checkout', '/other'),
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
            'sandbox_id': 'homepage-hero-heather', 'authorizer_id': 'LEGACY_FIXTURE',
            'source': {'channel_id': 'LEGACY_CHANNEL_FIXTURE', 'message_ts': 'legacy-fixture'},
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
        self.assertEqual(checker.HERO_BASE_COMMIT, '09a9d89b86586e9779454fcdb4911bda62dd03f9')
        self.assertEqual(checker.HERO_TEMPLATE_BASE_SHA256,
                         'f74d592ded8bfa7196061e8044040c86171f7d65118a145ea794d1212657c762')

    def test_original_provenance_is_pinned_to_real_source(self):
        spec = importlib.util.spec_from_file_location('production_checker', CHECKER)
        assert spec is not None and spec.loader is not None
        checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checker)
        self.assertEqual(checker.HERO_SOURCE_SHA256, '7b61ae81b9bd7f6a7cecc23f8a8f6c58a4fb1ebbc7e46fffc0499ca4f6e41643')
        self.assertEqual(checker.HERO_PUBLICATION_SOURCE_SHA256, 'c99b405655561a1af8a7ecbb0afa2fbe116bc1151ab567e00edcd36bc6defa71')

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
