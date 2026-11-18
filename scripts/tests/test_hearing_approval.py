"""Local synthetic authorization tests. Fixture identities are not real approvals."""
import copy
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
BASE = '8f27dc4f9639f11becba65876cb99148e823b66e'
CANDIDATE = 'ecf6122496fca1215afcc2751cdd6e6f04ccc579'
JS = 'assets/js/letter-content.js'
ICS = 'd65-board-meeting.ics'
CHECKER = 'scripts/sandbox_check.py'
TEST = 'scripts/tests/test_hearing_approval.py'
SOURCE = {'actor': 'FIXTURE_HUMAN', 'channel': 'FIXTURE_CHANNEL',
          'content_approval': 'FIXTURE_CONTENT_APPROVAL',
          'maintenance_approval': 'FIXTURE_MAINTENANCE_APPROVAL'}
SOURCE_PIN = hashlib.sha256(json.dumps(SOURCE, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
ENV = {'PATH': '/usr/bin:/bin', 'HOME': '/tmp', 'GIT_CONFIG_NOSYSTEM': '1',
       'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_TERMINAL_PROMPT': '0',
       'GIT_ALLOW_PROTOCOL': 'file', 'PYTHONDONTWRITEBYTECODE': '1'}


class HearingApprovalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='hearing-test-')
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / 'repo'
        subprocess.run(['git', '-c', 'core.hooksPath=/dev/null', 'clone', '-q', '--no-hardlinks',
                        '--no-checkout', str(ROOT), str(self.repo)], env=ENV, check=True, capture_output=True)
        self.git('checkout', '-q', 'sandbox/closure-hearings')
        self.git('reset', '--hard', CANDIDATE)
        self.git('update-ref', 'refs/remotes/origin/main', BASE)
        checker, count = re.subn(
            r'^HEARING_SOURCE_DIGEST = (?:None|[\"\x27][0-9a-f]{64}[\"\x27])$',
            f'HEARING_SOURCE_DIGEST = {SOURCE_PIN!r}', (ROOT / CHECKER).read_text(), flags=re.MULTILINE)
        if count != 1:
            raise ValueError('expected exactly one source-digest assignment')
        (self.repo / CHECKER).write_text(checker)
        (self.repo / TEST).write_bytes((ROOT / TEST).read_bytes())
        self.git('add', CHECKER, TEST)
        self.git('commit', '-qm', 'synthetic checker maintenance')
        self.path = Path(self.temp.name) / 'approval.json'
        self.record = self.make_record()

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.repo), '-c', 'core.hooksPath=/dev/null',
                               '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.test', *args],
                              env=ENV, check=True, capture_output=True, text=True).stdout

    def make_record(self):
        baseline = subprocess.run(['git', '-C', str(self.repo), 'show', BASE + ':' + ICS],
                                  env=ENV, check=True, capture_output=True).stdout
        return {'version': 1, 'purpose': 'closure-hearings', 'sandbox_id': 'closure-hearings',
                'source': copy.deepcopy(SOURCE), 'checkout': str(self.repo.resolve()),
                'base_commit': BASE, 'candidate_commit': CANDIDATE,
                'head_commit': self.git('rev-parse', 'HEAD').strip(),
                'files': [{'path': p, 'sha256': hashlib.sha256((self.repo / p).read_bytes()).hexdigest()}
                          for p in (JS, CHECKER, TEST)],
                'deleted': {'path': ICS, 'base_sha256': hashlib.sha256(baseline).hexdigest()}}

    def check(self, record=None, args=(), mode=0o600):
        self.path.write_text(json.dumps(self.record if record is None else record))
        self.path.chmod(mode)
        p = subprocess.run([sys.executable, str(self.repo / CHECKER), '--json',
                            '--hearing-approval-file', str(self.path), *args],
                           env=ENV, capture_output=True, text=True)
        return p.returncode, json.loads(p.stdout) if p.stdout.startswith('{') else p.stderr

    def test_exact_approved_candidate_passes_without_invented_vote_hold(self):
        code, report = self.check()
        self.assertEqual(code, 0, report)
        self.assertFalse(report['blocking'], report)
        self.assertTrue(any('team' in x.lower() and 'vote' in x.lower() for x in report['notes']), report)

    def test_approval_fields_are_bound_and_cannot_be_self_asserted(self):
        for key, value in [('source', dict(SOURCE, actor='IMPOSTOR')), ('base_commit', '0'*40),
                           ('candidate_commit', '0'*40), ('head_commit', '0'*40),
                           ('checkout', '/elsewhere'), ('files', []), ('version', True)]:
            record = copy.deepcopy(self.record); record[key] = value
            with self.subTest(key=key):
                code, report = self.check(record)
                self.assertEqual(code, 1, report)
                self.assertTrue(any('Invalid hearing approval' in b for b in report['blocking']), report)
        self.assertEqual(self.check(mode=0o644)[0], 1)
        self.assertEqual(self.check(args=('--base', BASE))[0], 1)
        self.git('checkout', '-qb', 'sandbox/other')
        self.assertEqual(self.check()[0], 1)

    def test_stale_dirty_or_hidden_files_are_rejected(self):
        p = self.repo / JS
        original = p.read_bytes(); p.write_bytes(original + b'\n')
        self.assertEqual(self.check()[0], 1)
        p.write_bytes(original)
        self.git('update-index', '--assume-unchanged', JS)
        self.assertEqual(self.check()[0], 1)
        self.git('update-index', '--no-assume-unchanged', JS)
        (self.repo / ICS).write_text('reappeared')
        self.assertEqual(self.check()[0], 1)

    def test_fresh_hashes_do_not_authorize_changes_to_candidate_or_extra_maintenance(self):
        for name in (JS, 'data/news.json', 'docs/unapproved.md'):
            p = self.repo / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes((p.read_bytes() if p.exists() else b'') + b'\nfixture tamper\n')
            self.git('add', name); self.git('commit', '-qm', 'tamper')
            code, report = self.check(self.make_record())
            self.assertEqual(code, 1, report)
            self.git('reset', '--hard', 'HEAD~1')

    def test_reviewed_help_build_outputs_are_bounded_maintenance(self):
        paths = ('docs/agents/fabian-website.md', 'docs/help/team-help.md',
                 'docs/help/team-help.pdf', 'docs/help/reviewed-sources.json')
        for name in paths:
            p = self.repo / name
            p.write_bytes(p.read_bytes() + b'\nfixture maintenance\n')
        self.git('add', *paths); self.git('commit', '-qm', 'fixture guide and help maintenance')
        record = self.make_record()
        record['files'].extend({'path': name, 'sha256': hashlib.sha256((self.repo / name).read_bytes()).hexdigest()}
                               for name in paths)
        code, report = self.check(record)
        self.assertEqual(code, 0, report)

    def test_unpopulated_provenance_pin_fails_closed(self):
        target = self.repo / CHECKER
        target.write_text(target.read_text().replace(repr(SOURCE_PIN), 'None'))
        self.git('add', CHECKER); self.git('commit', '-qm', 'unpopulated source pin')
        code, report = self.check(self.make_record())
        self.assertEqual(code, 1, report)
        self.assertTrue(any('Invalid hearing approval' in b for b in report['blocking']), report)

    def test_unrelated_ignored_file_is_not_a_universal_blocker(self):
        ignore = Path(self.temp.name) / 'fixture-ignore'
        ignore.write_text('temporary-cache.txt\n')
        self.git('config', 'core.excludesFile', str(ignore))
        (self.repo / 'temporary-cache.txt').write_text('fixture')
        code, report = self.check()
        self.assertEqual(code, 0, report)

    def test_source_pin_does_not_replace_valid_actor_and_approval_fields(self):
        malformed = {'actor': 'FIXTURE_HUMAN'}
        pin = hashlib.sha256(json.dumps(malformed, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        target = self.repo / CHECKER
        target.write_text(target.read_text().replace(SOURCE_PIN, pin))
        self.git('add', CHECKER); self.git('commit', '-qm', 'fixture malformed source pin')
        record = self.make_record(); record['source'] = malformed
        code, report = self.check(record)
        self.assertEqual(code, 1, report)

    def test_missing_record_and_extra_blocker_are_not_suppressed(self):
        p = subprocess.run([sys.executable, str(self.repo / CHECKER), '--json'], env=ENV, capture_output=True, text=True)
        report = json.loads(p.stdout)
        self.assertTrue(any(JS in b for b in report['blocking']), report)
        self.assertTrue(any(ICS in b for b in report['blocking']), report)
        self.assertTrue(any(CHECKER in b for b in report['blocking']), report)
        # Generic controls continue to run: pass a second invalid existing approval.
        code, report = self.check(args=('--approval-file', str(self.path)))
        self.assertEqual(code, 1, report)
        self.assertTrue(any('Invalid scoped approval' in b for b in report['blocking']), report)


if __name__ == '__main__':
    unittest.main()
