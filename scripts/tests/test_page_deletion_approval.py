import hashlib
import copy
import importlib.util
import json
import os
from pathlib import Path

import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

CHECKER = Path(__file__).resolve().parents[1] / 'sandbox_check.py'
PAGES = (
    'home/poll-results/index.html', 'es/resultados-encuesta/index.html',
    'home/a-brighter-path-forward/index.html', 'es/un-camino-mejor/index.html',
)
MAINTENANCE = (
    'scripts/sandbox_check.py', 'scripts/tests/test_page_deletion_approval.py',
    'docs/agents/fabian-website.md', 'docs/agents/fabian-website-cards.md',
    'docs/help/team-help.md', 'docs/help/team-help.pdf', 'docs/help/reviewed-sources.json',
)


class PageDeletionApprovalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'repo'
        self.root.mkdir()
        self.git('init', '-q', '-b', 'main')
        self.git('config', 'user.email', 'test@example.test')
        self.git('config', 'user.name', 'Test')
        checker_text = CHECKER.read_text(encoding='utf-8')
        fake_provenance = {'authorizer_id': 'USER_FIXTURE', 'source': {'channel_id': 'CHANNEL_FIXTURE', 'message_ts': 'delete-test'}}
        fake_delete = hashlib.sha256(json.dumps(fake_provenance, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        fake_provenance['source']['message_ts'] = 'maintenance-test'
        fake_maintenance = hashlib.sha256(json.dumps(fake_provenance, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        checker_text = checker_text.replace('d4588736ee5c89890031e4790ed1b86469fbe44e494f3c7783fb69c86a32730a', fake_delete)
        checker_text = checker_text.replace('87fd6aace394248871cd3bf2d3af9ce9a5e3abcc567160dd973ed79997daf0c6', fake_maintenance)
        self.write('scripts/sandbox_check.py', checker_text.encode())
        for path in PAGES:
            self.write(path, ('base page ' + path).encode())
        self.write('other/index.html', b'other page')
        self.git('add', '-A')
        self.git('commit', '-qm', 'base')
        self.base = self.git('rev-parse', 'HEAD').strip()
        self.git('update-ref', 'refs/remotes/origin/main', self.base)
        self.git('checkout', '-qb', 'sandbox/nov16-meeting')
        for path in PAGES:
            (self.root / path).unlink()
        self.git('add', '-A')
        self.git('commit', '-qm', 'four deletions')
        self.approval = Path(self.temp.name) / 'deletion.json'
        self.record = {
            'version': 1, 'purpose': 'nov16-page-deletion', 'sandbox_id': 'nov16-meeting',
            'authorizer_id': 'USER_FIXTURE',
            'source': {'channel_id': 'CHANNEL_FIXTURE', 'message_ts': 'delete-test'},
            'checkout': str(self.root.resolve()), 'base_commit': self.base,
            'head_commit': self.git('rev-parse', 'HEAD').strip(),
            'files': [{'path': p, 'sha256': hashlib.sha256(
                self.git_bytes('show', f'{self.base}:{p}')).hexdigest()} for p in PAGES],
        }

    def write(self, path, contents):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(contents)

    def git_bytes(self, *args):
        return subprocess.run(['git', '-C', str(self.root), *args], check=True, capture_output=True).stdout

    def git(self, *args):
        return self.git_bytes(*args).decode()

    def check(self, approval=True, extra=(), write=True):
        argv = [sys.executable, str(self.root / 'scripts/sandbox_check.py'), '--json', *extra]
        if approval:
            if write:
                self.approval.write_text(json.dumps(self.record))
                self.approval.chmod(0o600)
            argv += ['--deletion-approval-file', str(self.approval)]
        result = subprocess.run(argv, capture_output=True, text=True)
        self.assertEqual(result.stderr, '')
        return result.returncode, json.loads(result.stdout)

    def make_maintenance(self) -> dict:
        for path in MAINTENANCE:
            if path != 'scripts/sandbox_check.py':
                self.write(path, ('reviewed ' + path).encode())
        self.git('add', '-A')
        self.git('commit', '-qm', 'maintenance')
        self.record['head_commit'] = self.git('rev-parse', 'HEAD').strip()
        record = dict(self.record, purpose='nov16-checker-maintenance',
                      source={'channel_id': 'CHANNEL_FIXTURE', 'message_ts': 'maintenance-test'},
                      files=[{'path': p, 'sha256': hashlib.sha256((self.root / p).read_bytes()).hexdigest()}
                             for p in MAINTENANCE])
        return record

    def maintenance_check(self, record, write=True):
        path = Path(self.temp.name) / 'maintenance.json'
        if write:
            path.write_text(json.dumps(record))
            path.chmod(0o600)
        return self.check(extra=['--nov16-maintenance-approval-file', str(path)])

    def test_new_exception_does_not_publish_private_provenance(self):
        import re
        text = CHECKER.read_text(encoding='utf-8')
        section = text.split('NOV16_PAGES =', 1)[1].split('def unique_json_fields', 1)[0]
        self.assertIsNone(re.search(r'\b179[0-9]{7}\.[0-9]{6}\b', section))
        self.assertIsNone(re.search(r'\b[UC][0-9A-Z]{10}\b', section))

    def test_exact_four_committed_deletions_require_valid_approval(self):
        code, report = self.check(approval=False)
        self.assertEqual(code, 1, report)
        code, report = self.check()
        self.assertEqual(code, 0, report)
        self.assertEqual(len(report['changes']), 4)

    def test_separate_maintenance_approval_allows_only_exact_committed_inventory(self):
        record = self.make_maintenance()
        self.assertEqual(self.check()[0], 1)
        code, report = self.maintenance_check(record)
        self.assertEqual(code, 0, report)

    def test_deletion_record_identity_schema_and_binding_fail_closed(self):
        original = copy.deepcopy(self.record)
        for key, value in [
            ('version', True), ('purpose', 'nov16-checker-maintenance'),
            ('sandbox_id', 'other'), ('authorizer_id', 'OTHER_USER'),
            ('source', {'channel_id': 'CHANNEL_FIXTURE', 'message_ts': 'maintenance-test'}),
            ('source', {'channel_id': 'OTHER', 'message_ts': 'delete-test'}),
            ('checkout', '/wrong/checkout'), ('base_commit', '0' * 40),
            ('head_commit', '0' * 40), ('extra', 'not permitted'),
            ('files', []), ('files', original['files'][:-1]),
            ('files', original['files'] + [original['files'][0]]),
            ('files', original['files'] + [{'path': 'other/index.html', 'sha256': '0' * 64}]),
            ('files', [None]),
        ]:
            with self.subTest(key=key, value=value):
                self.record = copy.deepcopy(original)
                self.record[key] = value
                self.assertEqual(self.check()[0], 1)
        self.record = original
        for item in self.record['files']:
            old = item['sha256']
            item['sha256'] = '0' * 64
            self.assertEqual(self.check()[0], 1)
            item['sha256'] = old
        self.assertEqual(self.check(extra=['--base', self.base])[0], 1)
        self.git('checkout', '-qb', 'sandbox/other')
        self.assertEqual(self.check()[0], 1)

    def test_extra_or_substitute_deletions_are_blocked_even_with_matching_head(self):
        (self.root / 'other/index.html').unlink()
        self.git('add', '-A')
        self.git('commit', '-qm', 'extra deletion')
        self.record['head_commit'] = self.git('rev-parse', 'HEAD').strip()
        code, report = self.check()
        self.assertEqual(code, 1, report)
        self.assertTrue(any('other/index.html' in item for item in report['blocking']))
        self.git('checkout', self.base, '--', PAGES[0])
        self.git('commit', '-qm', 'restore one approved page')
        self.record['head_commit'] = self.git('rev-parse', 'HEAD').strip()
        self.assertEqual(self.check()[0], 1)

    def test_working_reappearance_staged_reappearance_and_symlink_are_rejected(self):
        target = self.root / PAGES[0]
        target.write_bytes(b'reappeared')
        self.assertEqual(self.check()[0], 1)
        self.git('add', PAGES[0])
        target.unlink()
        self.assertEqual(self.check()[0], 1)
        self.git('reset', '-q', 'HEAD', '--', PAGES[0])
        target.symlink_to('nonexistent')
        self.assertEqual(self.check()[0], 1)

    def test_private_records_permissions_symlinks_bad_json_and_owner(self):
        self.assertEqual(self.check()[0], 0)
        for mode in (0o644, 0o700):
            self.approval.chmod(mode)
            self.assertEqual(self.check(write=False)[0], 1)
        self.approval.chmod(0o600)
        real = self.approval.with_suffix('.real')
        self.approval.rename(real)
        self.approval.symlink_to(real)
        self.assertEqual(self.check(write=False)[0], 1)
        self.approval.unlink()
        self.approval.write_text('{"version":1,"version":1}')
        self.approval.chmod(0o600)
        self.assertEqual(self.check(write=False)[0], 1)
        self.approval.write_bytes(b'\xff')
        self.assertEqual(self.check(write=False)[0], 1)
        self.approval = self.root / 'private.json'
        self.assertEqual(self.check()[0], 1)
        self.approval = real
        spec = importlib.util.spec_from_file_location('deletion_checker', self.root / 'scripts/sandbox_check.py')
        assert spec is not None and spec.loader is not None
        checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checker)
        with patch.object(checker.os, 'getuid', return_value=os.getuid() + 1):
            with self.assertRaisesRegex(ValueError, 'operator-owned'):
                checker.load_nov16_deletion_approval(str(real), 'origin/main', None)

    def test_wrong_url_and_changed_base_and_head_are_rejected(self):
        spec = importlib.util.spec_from_file_location('deletion_checker_url', self.root / 'scripts/sandbox_check.py')
        assert spec is not None and spec.loader is not None
        checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checker)
        self.check()
        for url in ('http://forabrighterevanston.org/sandbox/nov16-meeting/',
                    'https://forabrighterevanston.org/sandbox/other/',
                    'https://forabrighterevanston.org/sandbox/nov16-meeting/?x=1'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                checker.load_nov16_deletion_approval(str(self.approval), 'origin/main', url)
        self.git('commit', '--allow-empty', '-qm', 'new head')
        self.assertEqual(self.check()[0], 1)
        self.record['head_commit'] = self.git('rev-parse', 'HEAD').strip()
        self.git('update-ref', 'refs/remotes/origin/main', self.record['head_commit'])
        self.assertEqual(self.check()[0], 1)

    def test_maintenance_record_rejects_wrong_inventory_identity_and_bytes(self):
        record = self.make_maintenance()
        for key, value in [('authorizer_id', 'OTHER_USER'), ('purpose', 'nov16-page-deletion'),
                           ('source', self.record['source']), ('checkout', '/wrong'),
                           ('base_commit', '0' * 40), ('head_commit', '0' * 40),
                           ('files', record['files'][:-1]),
                           ('files', record['files'] + [record['files'][0]]),
                           ('files', record['files'] + [{'path': 'scripts/other.py', 'sha256': '0' * 64}])]:
            with self.subTest(key=key):
                bad = copy.deepcopy(record)
                bad[key] = value
                self.assertEqual(self.maintenance_check(bad)[0], 1)
        for i in range(len(record['files'])):
            bad = copy.deepcopy(record)
            bad['files'][i]['sha256'] = '0' * 64
            self.assertEqual(self.maintenance_check(bad)[0], 1)
        target = self.root / 'docs/help/team-help.md'
        target.write_text('uncommitted tampering')
        self.assertEqual(self.maintenance_check(record)[0], 1)
        bad = copy.deepcopy(record)
        next(i for i in bad['files'] if i['path'] == 'docs/help/team-help.md')['sha256'] = hashlib.sha256(target.read_bytes()).hexdigest()
        self.assertEqual(self.maintenance_check(bad)[0], 1)

    def test_maintenance_does_not_authorize_other_restricted_paths(self):
        record = self.make_maintenance()
        for name in ('docs/other.md', 'scripts/other.py'):
            self.write(name, b'unauthorized')
        self.git('add', '-A')
        self.git('commit', '-qm', 'other paths')
        head = self.git('rev-parse', 'HEAD').strip()
        self.record['head_commit'] = record['head_commit'] = head
        code, report = self.maintenance_check(record)
        self.assertEqual(code, 1, report)
        for name in ('docs/other.md', 'scripts/other.py'):
            self.assertTrue(any(name in item for item in report['blocking']), report)

    def test_maintenance_record_permissions_and_file_modes(self):
        record = self.make_maintenance()
        self.assertEqual(self.maintenance_check(record)[0], 0)
        approval = Path(self.temp.name) / 'maintenance.json'
        approval.chmod(0o644)
        self.assertEqual(self.maintenance_check(record, write=False)[0], 1)
        approval.chmod(0o600)
        saved = approval.with_suffix('.real')
        approval.rename(saved)
        approval.symlink_to(saved)
        self.assertEqual(self.maintenance_check(record, write=False)[0], 1)
        approval.unlink()
        target = self.root / 'docs/help/team-help.md'
        target.chmod(0o755)
        self.assertEqual(self.maintenance_check(record)[0], 1)
        target.chmod(0o644)
        target.unlink()
        target.symlink_to('team-help.pdf')
        self.assertEqual(self.maintenance_check(record)[0], 1)

    def test_maintenance_staged_drift_and_committed_modes_cannot_be_hidden(self):
        record = self.make_maintenance()
        target = self.root / 'docs/help/team-help.md'
        original = target.read_bytes()
        target.write_bytes(b'staged tampering')
        self.git('add', 'docs/help/team-help.md')
        target.write_bytes(original)
        self.assertEqual(self.maintenance_check(record)[0], 1)
        self.git('reset', '-q', 'HEAD', '--', 'docs/help/team-help.md')
        self.git('update-index', '--chmod=+x', 'docs/help/team-help.md')
        self.git('commit', '-qm', 'executable')
        self.record['head_commit'] = record['head_commit'] = self.git('rev-parse', 'HEAD').strip()
        self.assertEqual(self.maintenance_check(record)[0], 1)

    def test_merge_base_must_equal_current_origin_main(self):
        self.git('checkout', '-qb', 'new-main', self.base)
        self.git('commit', '--allow-empty', '-qm', 'main advanced')
        newbase = self.git('rev-parse', 'HEAD').strip()
        self.git('update-ref', 'refs/remotes/origin/main', newbase)
        self.git('checkout', '-q', 'sandbox/nov16-meeting')
        self.record['base_commit'] = newbase
        self.assertEqual(self.check()[0], 1)


if __name__ == '__main__':
    unittest.main()
