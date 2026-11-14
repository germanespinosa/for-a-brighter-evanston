import copy
import hashlib
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
BASE_PIN = '5b14e14d977916a937effef74dcc5cb91122efe3'
SOURCE_PIN = 'c216bf944d4b60ba8f9c3cc12f71e619021f68cba249e547ff453e50c0d1aa30'
MAINTENANCE_SOURCE_PIN = '26ffb965db9260b8afff15da6faf7bc1da000b4aab1de5915da82038806a88c1'
SOURCE = {'authorizer_id': 'DELEGATE_FIXTURE', 'source': {
    'date': {'authorizer_id': 'OWNER_FIXTURE', 'channel_id': 'CHANNEL_FIXTURE',
             'message_ts': 'approval-fixture', 'question_ts': 'question-fixture'},
    'delegation': {'authorizer_id': 'OWNER_FIXTURE', 'channel_id': 'CHANNEL_FIXTURE', 'message_ts': 'delegation-fixture'},
    'removal': {'authorizer_id': 'DELEGATE_FIXTURE', 'channel_id': 'CHANNEL_FIXTURE', 'message_ts': 'removal-fixture'},
    'confirmation': {'authorizer_id': 'DELEGATE_FIXTURE', 'channel_id': 'CHANNEL_FIXTURE', 'message_ts': 'post-delegation-fixture'}}}
MAINTENANCE_SOURCE = {'authorizer_id': 'DELEGATE_FIXTURE', 'source': {
    'delegation': copy.deepcopy(SOURCE['source']['delegation']),
    'maintenance': {'authorizer_id': 'DELEGATE_FIXTURE', 'channel_id': 'CHANNEL_FIXTURE',
                    'message_ts': 'maintenance-approval-fixture', 'question_ts': 'maintenance-question-fixture'}}}
JS = 'assets/js/letter-content.js'
MAINTENANCE = ('scripts/sandbox_check.py', 'scripts/tests/test_letter_vote_approval.py',
               'docs/agents/fabian-website.md', 'docs/agents/fabian-website-cards.md',
               'docs/help/team-help.md', 'docs/help/team-help.pdf', 'docs/help/reviewed-sources.json')
CHANGES = (
    ('D65 describes November 9 as a plan vote, with closure hearings and later final action still to follow.',
     'The board is expected to vote on the plan on November 16, with closure hearings and any final closure decision to follow.'),
    ('El D65 describe la votación del 9 de noviembre como una votación sobre el plan, a la que todavía seguirían audiencias sobre los cierres y una decisión final posterior.',
     'Se espera que la Junta vote sobre el plan el 16 de noviembre; después seguirían audiencias sobre los cierres y cualquier decisión final al respecto.'),
)


class LetterVoteApprovalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'repo'
        self.root.mkdir()
        self.git('init', '-q', '-b', 'main')
        self.git('config', 'user.email', 'test@example.test')
        self.git('config', 'user.name', 'Test')
        fake = hashlib.sha256(json.dumps(SOURCE, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        maintenance_fake = hashlib.sha256(json.dumps(MAINTENANCE_SOURCE, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        text = CHECKER.read_text().replace(SOURCE_PIN, fake).replace(MAINTENANCE_SOURCE_PIN, maintenance_fake)
        self.write('scripts/sandbox_check.py', text.encode())
        realroot = Path(__file__).resolve().parents[2]
        baseline = subprocess.run(['git', '-C', str(realroot), 'show', f'{BASE_PIN}:{JS}'],
                                  check=True, capture_output=True).stdout
        self.write(JS, baseline)
        self.write('assets/js/letter.js', b'unchanged js\n')
        self.write('data/news.json', b'{}\n')
        for path in MAINTENANCE[2:]:
            self.write(path, ('base ' + path).encode())
        self.git('add', '-A')
        self.git('commit', '-qm', 'base')
        self.base = self.git('rev-parse', 'HEAD').strip()
        self.git('update-ref', 'refs/remotes/origin/main', self.base)
        self.git('checkout', '-qb', 'sandbox/letter-vote-nov16')
        checker = self.root / 'scripts/sandbox_check.py'
        checker.write_text(checker.read_text().replace(BASE_PIN, self.base))
        self.write(MAINTENANCE[1], b'new reviewed tests\n')
        for before, after in CHANGES:
            self.assertEqual(baseline.count(before.encode()), 1)
            baseline = baseline.replace(before.encode(), after.encode())
        for title in (b'School Age Child Care (SACC)', b'Cuidado infantil escolar (SACC)'):
            marker = b'      {\n        "title": "' + title + b'",'
            self.assertEqual(baseline.count(marker), 1)
            start = baseline.index(marker)
            end = baseline.index(b'\n      },\n', start) + len(b'\n      },\n')
            baseline = baseline[:start] + baseline[end:]
        self.write(JS, baseline)
        self.git('add', '-A')
        self.git('commit', '-qm', 'approved copy and maintenance')
        self.paths = [Path(self.temp.name) / 'copy.json', Path(self.temp.name) / 'maintenance.json']
        self.records = [self.record('letter-vote-copy', (JS,)),
                        self.record('letter-vote-maintenance', MAINTENANCE)]

    def write(self, path, data):
        p = self.root / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.root), *args], check=True, capture_output=True, text=True).stdout

    def record(self, purpose, paths):
        return {'version': 1, 'purpose': purpose, 'sandbox_id': 'letter-vote-nov16',
                **copy.deepcopy(SOURCE if purpose == 'letter-vote-copy' else MAINTENANCE_SOURCE), 'checkout': str(self.root.resolve()),
                'base_commit': self.base, 'head_commit': self.git('rev-parse', 'HEAD').strip(),
                'files': [{'path': p, 'sha256': hashlib.sha256((self.root / p).read_bytes()).hexdigest()}
                          for p in paths]}

    def check(self, use=(True, True), write=True, extra=()):
        argv = [sys.executable, str(self.root / 'scripts/sandbox_check.py'), '--json', *extra]
        for enabled, path, record, flag in zip(use, self.paths, self.records,
                ('--letter-vote-approval-file', '--letter-vote-maintenance-approval-file')):
            if enabled:
                if write:
                    path.write_text(json.dumps(record))
                    path.chmod(0o600)
                argv.extend((flag, str(path)))
        result = subprocess.run(argv, capture_output=True, text=True)
        self.assertEqual(result.stderr, '')
        return result.returncode, json.loads(result.stdout)

    def test_exact_committed_copy_and_separate_maintenance_need_both_records(self):
        self.assertEqual(self.check((False, False))[0], 1)
        self.assertEqual(self.check((True, False))[0], 1)
        self.assertEqual(self.check((False, True))[0], 1)
        code, report = self.check()
        self.assertEqual(code, 0, report)

    def test_content_provenance_does_not_authorize_maintenance(self):
        self.records[1]['source'] = copy.deepcopy(SOURCE['source'])
        code, report = self.check()
        self.assertEqual(code, 1, report)
        self.assertTrue(any('Invalid letter-vote-maintenance approval' in x for x in report['blocking']), report)

    def test_delegate_maintenance_is_not_mislabeled_as_owner_authorized(self):
        code, report = self.check()
        self.assertEqual(code, 0, report)
        self.assertTrue(any('Delegate-authorized fixed-inventory maintenance' in x for x in report['changes']), report)
        self.assertFalse(any('German-authorized fixed-inventory maintenance' in x for x in report['changes']), report)

    def test_bilingual_sacc_removal_with_date_is_accepted_only_when_exact(self):
        self.assertNotIn(b'SACC', (self.root / JS).read_bytes())
        code, report = self.check()
        self.assertEqual(code, 0, report)

    def test_each_independent_provenance_component_is_required(self):
        self.assertEqual(self.check()[0], 0)
        for i in (0, 1):
            original = copy.deepcopy(self.records[i])
            for component in original['source']:
                for field in original['source'][component]:
                    with self.subTest(record=i, component=component, field=field):
                        self.records[i] = copy.deepcopy(original)
                        self.records[i]['source'][component][field] = 'wrong'
                        self.assertEqual(self.check()[0], 1)
                self.records[i] = copy.deepcopy(original)
                del self.records[i]['source'][component]
                self.assertEqual(self.check()[0], 1)
            self.records[i] = original

    def test_one_sacc_language_restored_is_rejected_with_fresh_hashes(self):
        base = subprocess.run(['git', '-C', str(self.root), 'show', f'{self.base}:{JS}'],
                              check=True, capture_output=True).stdout
        for title in (b'School Age Child Care (SACC)', b'Cuidado infantil escolar (SACC)'):
            target = self.root / JS
            original = target.read_bytes()
            marker = b'      {\n        "title": "' + title + b'",'
            start = base.index(marker)
            end = base.index(b'\n      },\n', start) + len(b'\n      },\n')
            anchor = b'      {\n        "title": "' + (b'TWI and bilingual parent participation' if title.startswith(b'School') else b'TWI y participaci')
            self.assertEqual(original.count(anchor), 1)
            target.write_bytes(original.replace(anchor, base[start:end] + anchor, 1))
            self.commit('restore one SACC language')
            self.assertEqual(self.check()[0], 1)
            self.git('reset', '--hard', 'HEAD~1')
            self.update_records()

    def test_date_only_legacy_provenance_never_authorizes_expanded_copy(self):
        self.records[0]['authorizer_id'] = 'OWNER_FIXTURE'
        self.records[0]['source'] = copy.deepcopy(SOURCE['source']['date'])
        self.assertEqual(self.check()[0], 1)

    def test_ignored_untracked_javascript_cannot_bypass_exact_scope(self):
        self.git('config', 'core.excludesFile', str(Path(self.temp.name) / 'ignore'))
        (Path(self.temp.name) / 'ignore').write_text('assets/js/hidden.js\n')
        self.write('assets/js/hidden.js', b'evil();\n')
        code, report = self.check()
        self.assertEqual(code, 1, report)

    def test_records_reject_wrong_schema_provenance_or_binding(self):
        for i in (0, 1):
            original = copy.deepcopy(self.records[i])
            for key, value in (
                ('version', True), ('purpose', 'other'), ('sandbox_id', 'other'),
                ('authorizer_id', 'OTHER'), ('source', {'channel_id': 'other', 'message_ts': 'approval-fixture', 'question_ts': 'question-fixture'}),
                ('source', {'channel_id': 'CHANNEL_FIXTURE', 'message_ts': 'approval-fixture', 'question_ts': 'other'}),
                ('checkout', '/wrong'), ('base_commit', '0' * 40), ('head_commit', '0' * 40),
                ('extra', 1), ('files', []), ('files', [None]),
                ('files', original['files'] + [original['files'][0]]),
                ('files', original['files'] + [{'path': 'assets/js/letter.js', 'sha256': '0' * 64}]),
            ):
                with self.subTest(record=i, key=key, value=value):
                    self.records[i] = copy.deepcopy(original)
                    self.records[i][key] = value
                    self.assertEqual(self.check()[0], 1)
            for n in range(len(original['files'])):
                self.records[i] = copy.deepcopy(original)
                self.records[i]['files'][n]['sha256'] = '0' * 64
                self.assertEqual(self.check()[0], 1)
            self.records[i] = original
        self.assertEqual(self.check(extra=['--base', self.base])[0], 1)
        self.git('checkout', '-qb', 'sandbox/other')
        self.assertEqual(self.check()[0], 1)

    def update_records(self):
        for record in self.records:
            record['head_commit'] = self.git('rev-parse', 'HEAD').strip()
            for item in record['files']:
                target = self.root / item['path']
                if target.is_file():
                    item['sha256'] = hashlib.sha256(target.read_bytes()).hexdigest()

    def commit(self, message):
        self.git('add', '-A')
        self.git('commit', '-qm', message)
        self.update_records()

    def test_byte_level_copy_tampering_rejected_even_with_matching_hashes(self):
        target = self.root / JS
        target.write_bytes(target.read_bytes() + b'\nalert(1);\n')
        self.commit('extra executable code')
        code, report = self.check()
        self.assertEqual(code, 1, report)
        self.assertTrue(any('exactly the approved' in x for x in report['blocking']), report)

    def test_one_substitution_only_is_not_authorized(self):
        target = self.root / JS
        before, after = CHANGES[1]
        target.write_bytes(target.read_bytes().replace(after.encode(), before.encode()))
        self.commit('remove one substitution')
        self.assertEqual(self.check()[0], 1)

    def test_changed_other_javascript_and_live_data_are_blocked(self):
        for name in ('assets/js/letter.js', 'data/news.json', 'docs/unrelated.md'):
            with self.subTest(name=name):
                self.write(name, b'unauthorized')
                self.commit('unrelated change')
                code, report = self.check()
                self.assertEqual(code, 1, report)
                self.assertTrue(any(name in x for x in report['blocking']), report)
                self.git('reset', '--hard', 'HEAD~1')
                self.update_records()

    def test_dirty_index_worktree_and_untracked_files_fail_closed(self):
        target = self.root / JS
        original = target.read_bytes()
        target.write_bytes(original + b'extra')
        self.assertEqual(self.check()[0], 1)
        self.git('add', JS)
        target.write_bytes(original)
        self.assertEqual(self.check()[0], 1)
        self.git('reset', '-q', 'HEAD', '--', JS)
        self.write('data/news.json', b'dirty')
        self.assertEqual(self.check()[0], 1)
        self.git('restore', 'data/news.json')
        self.write('assets/js/new.js', b'extra')
        self.assertEqual(self.check()[0], 1)

    def test_assume_unchanged_cannot_hide_modified_live_data(self):
        self.git('update-index', '--assume-unchanged', 'data/news.json')
        self.write('data/news.json', b'hidden dirty data')
        code, report = self.check()
        self.assertEqual(code, 1, report)

    def test_modes_deletions_and_symlinks_fail_closed(self):
        target = self.root / MAINTENANCE[-1]
        target.chmod(0o755)
        self.assertEqual(self.check()[0], 1)
        target.chmod(0o644)
        target.unlink()
        self.assertEqual(self.check()[0], 1)
        target.symlink_to('team-help.pdf')
        self.assertEqual(self.check()[0], 1)

    def test_private_record_permissions_symlinks_bad_json_and_owner(self):
        self.assertEqual(self.check()[0], 0)
        for path in self.paths:
            for mode in (0o644, 0o400, 0o700):
                path.chmod(mode)
                self.assertEqual(self.check(write=False)[0], 1)
            path.chmod(0o600)
            real = path.with_suffix('.real')
            path.rename(real)
            path.symlink_to(real)
            self.assertEqual(self.check(write=False)[0], 1)
            path.unlink()
            real.rename(path)
            saved = path.read_bytes()
            path.write_text('{"version":1,"version":1}')
            self.assertEqual(self.check(write=False)[0], 1)
            path.write_bytes(b'\xff')
            self.assertEqual(self.check(write=False)[0], 1)
            path.write_bytes(saved)
        old = sys.dont_write_bytecode
        sys.dont_write_bytecode = True
        self.addCleanup(setattr, sys, 'dont_write_bytecode', old)
        spec = importlib.util.spec_from_file_location('letter_checker_fixture', self.root / 'scripts/sandbox_check.py')
        assert spec is not None and spec.loader is not None
        checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checker)
        with patch.object(checker.os, 'getuid', return_value=os.getuid() + 1):
            with self.assertRaisesRegex(ValueError, 'operator-owned'):
                checker.load_letter_vote_approval(self.paths[0], 'letter-vote-copy', 'origin/main', None)

    def test_sandbox_url_and_head_and_base_binding(self):
        self.check()
        old = sys.dont_write_bytecode
        sys.dont_write_bytecode = True
        self.addCleanup(setattr, sys, 'dont_write_bytecode', old)
        spec = importlib.util.spec_from_file_location('letter_checker_url', self.root / 'scripts/sandbox_check.py')
        assert spec is not None and spec.loader is not None
        checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checker)
        for url in ('http://forabrighterevanston.org/sandbox/letter-vote-nov16/',
                    'https://forabrighterevanston.org/sandbox/other/',
                    'https://forabrighterevanston.org/sandbox/letter-vote-nov16/?x=1'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                checker.load_letter_vote_approval(self.paths[0], 'letter-vote-copy', 'origin/main', url)
        self.git('commit', '--allow-empty', '-qm', 'new head')
        self.assertEqual(self.check()[0], 1)
        self.update_records()
        self.git('update-ref', 'refs/remotes/origin/main', self.records[0]['head_commit'])
        self.assertEqual(self.check()[0], 1)

    def test_base_content_pin_cannot_be_replaced_by_record_digest(self):
        checker = self.root / 'scripts/sandbox_check.py'
        checker.write_text(checker.read_text().replace(
            '090694a356a8020db6d7d5df48d22e180b2b5a51a3ce2db66caab83d8e695b32', '0' * 64))
        self.commit('invalid baseline pin')
        code, report = self.check()
        self.assertEqual(code, 1, report)
        self.assertTrue(any('baseline SHA-256' in x for x in report['blocking']), report)


    def test_publication_guard_rejects_advanced_remote_even_if_ancestor(self):
        manual = (Path(__file__).resolve().parents[2] / 'docs/agents/fabian-website.md').read_text()
        self.assertIn('core.hooksPath=<private-hook-dir>', manual)
        folder = self.root.parent
        remote, repo, hooks = folder / 'lease-remote.git', folder / 'lease-work', folder / 'lease-hooks'
        subprocess.run(['git', 'init', '--bare', '-q', str(remote)], check=True)
        subprocess.run(['git', 'init', '-q', '-b', 'main', str(repo)], check=True)
        def run(*args, check=True):
            return subprocess.run(['git', '-C', str(repo), *args], check=check, capture_output=True, text=True)
        run('config', 'user.email', 'fixture@example.test')
        run('config', 'user.name', 'Fixture')
        run('remote', 'add', 'origin', str(remote))
        run('commit', '--allow-empty', '-qm', 'base')
        base = run('rev-parse', 'HEAD').stdout.strip()
        run('push', '-q', 'origin', 'HEAD:refs/heads/main')
        run('commit', '--allow-empty', '-qm', 'intermediate')
        run('push', '-q', 'origin', 'HEAD:refs/heads/main')
        run('commit', '--allow-empty', '-qm', 'voted merge candidate')
        self.assertEqual(run('push', '--dry-run', 'origin', 'HEAD:refs/heads/main').returncode, 0)
        hooks.mkdir()
        hook = hooks / 'pre-push'
        hook.write_text('#!/bin/sh\ncount=0\nwhile read local_ref local_oid remote_ref remote_oid; do\n  count=$((count + 1))\n  [ "$remote_ref" = refs/heads/main ] && [ "$remote_oid" = "$FABIAN_EXPECTED_MAIN" ] || exit 1\ndone\n[ "$count" -eq 1 ]\n')
        hook.chmod(0o700)
        env = dict(os.environ, FABIAN_EXPECTED_MAIN=base)
        guarded = subprocess.run(['git', '-C', str(repo), '-c', f'core.hooksPath={hooks}', 'push', 'origin', 'HEAD:refs/heads/main'], env=env, capture_output=True, text=True)
        self.assertNotEqual(guarded.returncode, 0, guarded.stderr)
        actual = subprocess.check_output(['git', '--git-dir', str(remote), 'rev-parse', 'refs/heads/main'], text=True).strip()
        self.assertEqual(actual, run('rev-parse', 'HEAD^').stdout.strip())
        env['FABIAN_EXPECTED_MAIN'] = actual
        allowed = subprocess.run(['git', '-C', str(repo), '-c', f'core.hooksPath={hooks}', 'push', 'origin', 'HEAD:refs/heads/main'], env=env, capture_output=True, text=True)
        self.assertEqual(allowed.returncode, 0, allowed.stderr)
        self.assertEqual(subprocess.check_output(['git', '--git-dir', str(remote), 'rev-parse', 'refs/heads/main'], text=True).strip(), run('rev-parse', 'HEAD').stdout.strip())


if __name__ == '__main__':
    unittest.main()
