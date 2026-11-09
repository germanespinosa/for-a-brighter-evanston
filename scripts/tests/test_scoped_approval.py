"""Scoped permission CLI tests; all Git writes are disposable fixtures."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

CHECKER = Path(__file__).resolve().parents[1] / 'sandbox_check.py'
CSS = 'assets/css/release-home.css'


class ApprovalFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'repo'
        (self.root / 'scripts').mkdir(parents=True)
        shutil.copy2(CHECKER, self.root / 'scripts/sandbox_check.py')
        self.git('init', '-q', '-b', 'sandbox/poll-model-release')
        self.git('config', 'user.name', 'Test')
        self.git('config', 'user.email', 'test@example.invalid')
        self.git('add', '.')
        self.git('commit', '-qm', 'baseline')
        self.git('tag', 'baseline')
        self.approval = Path(self.temp.name) / 'approval.json'
        self.record: dict = dict(version=1, sandbox_id='poll-model-release', purpose='sandbox-review',
                           authorizer_id='U0CE2G08ZRC',
                           source=dict(channel_id='C0CEMKENSQ1', message_ts='1794230153.839529'),
                           css=[dict(path=CSS, routes=['/', '/es/'], scope='.release-home')], workbooks=[])

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.root), *args], check=True,
                              capture_output=True, text=True).stdout

    def write(self, path, content):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)

    def check(self, approval=True):
        self.git('add', '-A')
        self.git('commit', '--allow-empty', '-qm', 'change')
        argv = [sys.executable, str(self.root / 'scripts/sandbox_check.py'), '--base', 'baseline', '--json']
        if approval:
            self.approval.write_text(json.dumps(self.record))
            self.approval.chmod(0o600)
            argv += ['--approval-file', str(self.approval)]
        result = subprocess.run(argv, capture_output=True, text=True)
        self.assertEqual(result.stderr, '')
        return result.returncode, json.loads(result.stdout)

class ScopedApprovalTests(ApprovalFixture):
    def test_german_can_approve_exact_page_scoped_css(self):
        self.write(CSS, '.release-home .hero { color: navy; }\n@media (max-width: 600px) { .release-home .hero { padding: 1rem; } }')
        code, report = self.check()
        self.assertEqual(code, 0, report)
        self.assertTrue(any('sandbox-review' in item for item in report['notes']))

    def test_scoped_children_and_nested_siblings_remain_within_wrapper(self):
        self.write(CSS, '.release-home > .card { color: navy; }\n'
                   '.release-home .card + .card { margin: 1rem; }\n'
                   '.release-home #section .chart ~ p { color: navy; }\n'
                   '@media(max-width:760px) { .release-home .card { margin: 0; } }')
        code, report = self.check()
        self.assertEqual(code, 0, report)

    def test_kerstin_can_approve_same_class(self):
        self.record['authorizer_id'] = 'U0CE4NY7KC2'
        self.write(CSS, '.release-home { color: navy; }')
        self.assertEqual(self.check()[0], 0)

    def test_default_still_blocks_css(self):
        self.write(CSS, '.release-home { color: navy; }')
        self.assertEqual(self.check(approval=False)[0], 1)

    def test_unapproved_user_is_rejected(self):
        self.record['authorizer_id'] = 'UOTHER'
        self.write(CSS, '.release-home { color: navy; }')
        self.assertEqual(self.check()[0], 1)

    def test_mismatched_sandbox_is_rejected(self):
        self.record['sandbox_id'] = 'another-update'
        self.write(CSS, '.release-home { color: navy; }')
        self.assertEqual(self.check()[0], 1)

    def test_mismatched_route_is_rejected(self):
        self.record['css'][0]['routes'] = ['/unrelated/']
        self.write(CSS, '.release-home { color: navy; }')
        self.assertEqual(self.check()[0], 1)

    def test_approval_cannot_mint_another_css_path(self):
        self.record['css'][0]['path'] = 'assets/css/site.css'
        self.write('assets/css/site.css', 'body { color: navy; }')
        self.assertEqual(self.check()[0], 1)

    def test_unrelated_css_js_and_build_files_stay_blocked(self):
        for path in ('assets/css/site.css', 'assets/js/release.js', '_config.yml', 'docs/extra.md'):
            self.write(path, 'not authorized')
        code, report = self.check()
        self.assertEqual(code, 1)
        for path in ('assets/css/site.css', 'assets/js/release.js', '_config.yml', 'docs/extra.md'):
            self.assertTrue(any(path in b for b in report['blocking']), report)

    def test_global_css_and_unsafe_syntax_are_rejected(self):
        payloads = ['body { color:red; }', '.release-home, body { color:red; }',
                    '@import "https://evil.invalid/a.css";',
                    '.release-home { background: url(https://evil.invalid/x); }',
                    '.release-home { width: expression(evil()); }',
                    '.release-home + body { color:red; }',
                    '.release-home:hover + body { color:red; }',
                    '.release-home[data-flag="x"] ~ body { color:red; }',
                    r'.release-home { background: u\72l(https://evil.invalid/x); }']
        for payload in payloads:
            with self.subTest(payload=payload):
                self.write(CSS, payload)
                code, report = self.check()
                self.assertEqual(code, 1, report)

    def workbook(self, extras=None):
        import zipfile
        path = 'assets/files/d65-financial-model-v4.xlsx'
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(target, 'w') as archive:
            archive.writestr('[Content_Types].xml', '<Types><Override ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/></Types>')
            archive.writestr('xl/workbook.xml', '<workbook/>')
            archive.writestr('_rels/.rels', '<Relationships/>')
            for name, data in (extras or {}).items():
                archive.writestr(name, data)
        self.record['workbooks'] = [dict(path=path, sha256=hashlib.sha256(target.read_bytes()).hexdigest())]
        return target

    def test_exact_unchanged_macro_free_workbook_is_allowed(self):
        target = self.workbook()
        before = target.read_bytes()
        self.assertEqual(self.check()[0], 0)
        self.assertEqual(target.read_bytes(), before)

    def test_workbook_without_approval_is_rejected(self):
        self.workbook()
        self.assertEqual(self.check(approval=False)[0], 1)

    def test_workbook_digest_mismatch_is_rejected(self):
        self.workbook()
        self.record['workbooks'][0]['sha256'] = '0' * 64
        self.assertEqual(self.check()[0], 1)

    def test_unsafe_xlsx_even_with_matching_digest_is_rejected(self):
        payloads = [
            {'xl/vbaProject.bin': b'code'},
            {'xl/payload.js': b'code'},
            {'xl/arbitrary.bin': b'code'},
            {'xl/embeddings/object.bin': b'object'},
            {'xl/externalLinks/externalLink1.xml': '<externalLink/>'},
            {'xl/worksheets/_rels/sheet1.xml.rels': '<Relationships><Relationship TargetMode="External" Target="https://evil.invalid"/></Relationships>'},
            {'xl/worksheets/sheet1.xml': '<worksheet><f>WEBSERVICE("https://evil.invalid")</f></worksheet>'},
            {'xl/worksheets/sheet1.xml': '<!DOCTYPE x [<!ENTITY e "x">]><worksheet/>'},
            {'../payload': b'escape'},
        ]
        for extras in payloads:
            with self.subTest(extras=extras):
                self.workbook(extras)
                code, report = self.check()
                self.assertEqual(code, 1, report)

    def test_invalid_zip_disguised_as_xlsx_is_rejected(self):
        target = self.workbook()
        target.write_bytes(b'not a ZIP')
        self.record['workbooks'][0]['sha256'] = hashlib.sha256(target.read_bytes()).hexdigest()
        self.assertEqual(self.check()[0], 1)

    def test_all_three_exact_css_scopes_are_supported(self):
        for path, routes, scope in [
            ('assets/css/release-poll.css', ['/home/voter-poll/', '/es/encuesta/'], '.release-poll'),
            ('assets/css/release-path.css', ['/home/a-brighter-path-forward/', '/es/un-camino-mejor/'], '.release-path'),
        ]:
            self.record['css'].append(dict(path=path, routes=routes, scope=scope))
            self.write(path, scope + ' .card { color: navy; }')
        self.assertEqual(self.check()[0], 0)

    def test_malformed_or_missing_provenance_fails_closed(self):
        self.write(CSS, '.release-home { color: navy; }')
        for source in (None, {}, {'channel_id': 'OTHER', 'message_ts': '1794230153.839529'},
                       {'channel_id': 'C0CEMKENSQ1', 'message_ts': 'invalid'}):
            self.record['source'] = source
            self.assertEqual(self.check()[0], 1)

    def test_other_workbook_and_macro_extensions_stay_blocked(self):
        for path in ('assets/files/other.xlsx', 'assets/files/model.xlsm', 'assets/files/model.xls'):
            self.write(path, 'not approved')
        code, report = self.check()
        self.assertEqual(code, 1)
        self.assertEqual(len(report['blocking']), 3)

    def test_approval_inside_repository_is_rejected(self):
        self.approval = self.root / 'approval.json'
        self.write(CSS, '.release-home { color: navy; }')
        code, report = self.check()
        self.assertEqual(code, 1)
        self.assertTrue(any('outside the repository' in b for b in report['blocking']))

    def test_symlink_and_executable_assets_are_rejected(self):
        self.write('assets/css/target.txt', '.release-home { color: navy; }')
        (self.root / CSS).symlink_to('target.txt')
        code, report = self.check()
        self.assertEqual(code, 1)
        self.assertTrue(any(CSS in b and 'regular' in b for b in report['blocking']))
        (self.root / CSS).unlink()
        self.write(CSS, '.release-home { color: navy; }')
        (self.root / CSS).chmod(0o755)
        code, report = self.check()
        self.assertEqual(code, 1)
        self.assertTrue(any(CSS in b and 'non-executable' in b for b in report['blocking']))

    def test_private_record_permissions_and_symlinks_fail_closed(self):
        self.write(CSS, '.release-home { color: navy; }')
        self.assertEqual(self.check()[0], 0)
        argv = [sys.executable, str(self.root / 'scripts/sandbox_check.py'), '--base', 'baseline',
                '--approval-file', str(self.approval), '--json']
        self.approval.chmod(0o644)
        result = subprocess.run(argv, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('0600', result.stdout)
        original = self.approval.with_suffix('.original')
        self.approval.rename(original)
        self.approval.symlink_to(original)
        result = subprocess.run(argv, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('non-symlink', result.stdout)

    def test_wrong_url_and_publication_purpose_are_rejected(self):
        self.write(CSS, '.release-home { color: navy; }')
        self.assertEqual(self.check()[0], 0)
        argv = [sys.executable, str(self.root / 'scripts/sandbox_check.py'), '--base', 'baseline',
                '--approval-file', str(self.approval), '--json', '--url', 'https://forabrighterevanston.org/sandbox/other/']
        # Import and call only approval loading: no deployed network requests.
        import importlib.util
        spec = importlib.util.spec_from_file_location('approval_checker', self.root / 'scripts/sandbox_check.py')
        assert spec is not None and spec.loader is not None
        checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checker)
        with self.assertRaisesRegex(ValueError, 'deployed URL'):
            checker.load_scoped_approval(str(self.approval), argv[-1])
        self.record['purpose'] = 'live-publication'
        self.assertEqual(self.check()[0], 1)

    def test_uncommitted_asset_change_is_not_validated_as_head(self):
        self.write(CSS, '.release-home { color: navy; }')
        self.assertEqual(self.check()[0], 0)
        self.write(CSS, '.release-home { color: red; }')
        result = subprocess.run([sys.executable, str(self.root / 'scripts/sandbox_check.py'), '--base', 'baseline',
                                 '--approval-file', str(self.approval), '--json'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('committed revision', result.stdout)

    def test_scoped_asset_deletion_is_not_authorized(self):
        self.write(CSS, '.release-home { color: navy; }')
        self.git('add', '-A')
        self.git('commit', '-qm', 'live fixture')
        self.git('tag', '-f', 'baseline')
        (self.root / CSS).unlink()
        self.assertEqual(self.check()[0], 1)


MAINTENANCE_PATHS = (
    'docs/agents/fabian-website.md', 'docs/help/team-help.md',
    'docs/help/team-help.pdf', 'docs/help/reviewed-sources.json',
    'scripts/sandbox_check.py', 'scripts/tests/test_scoped_approval.py',
)


class MaintenanceApprovalTests(ApprovalFixture):
    def setUp(self):
        super().setUp()
        for path in MAINTENANCE_PATHS:
            if path != 'scripts/sandbox_check.py':
                self.write(path, 'reviewed maintenance fixture\n')
        self.git('add', '-A')
        self.git('commit', '-qm', 'maintenance fixture')
        self.maintenance = Path(self.temp.name) / 'maintenance.json'
        self.maintenance_record: dict = dict(
            version=1, purpose='delegation-maintenance', sandbox_id='poll-model-release',
            authorizer_id='U0CE2G08ZRC',
            source=dict(channel_id='C0CEMKENSQ1', message_ts='1794230153.839529'),
            files=[dict(path=p, sha256=hashlib.sha256((self.root / p).read_bytes()).hexdigest())
                   for p in MAINTENANCE_PATHS])

    def maintenance_check(self, record=True, asset=False, write_record=True):
        argv = [sys.executable, str(self.root / 'scripts/sandbox_check.py'),
                '--base', 'baseline', '--json']
        if record:
            if write_record:
                self.maintenance.write_text(json.dumps(self.maintenance_record))
                self.maintenance.chmod(0o600)
            argv += ['--maintenance-approval-file', str(self.maintenance)]
        if asset:
            self.approval.write_text(json.dumps(self.record))
            self.approval.chmod(0o600)
            argv += ['--approval-file', str(self.approval)]
        result = subprocess.run(argv, capture_output=True, text=True)
        self.assertEqual(result.stderr, '')
        return result.returncode, json.loads(result.stdout)

    def test_german_exact_maintenance_inventory_is_allowed(self):
        code, report = self.maintenance_check()
        self.assertEqual(code, 0, report)
        self.assertTrue(any('maintenance' in n.lower() for n in report['notes']))


    def test_no_maintenance_record_leaves_docs_and_scripts_blocked(self):
        code, report = self.maintenance_check(record=False)
        self.assertEqual(code, 1, report)
        for path in MAINTENANCE_PATHS:
            if path != 'scripts/sandbox_check.py':  # unchanged in this fixture
                self.assertTrue(any(path in b for b in report['blocking']), report)

    def test_asset_record_never_waives_maintenance(self):
        code, report = self.maintenance_check(record=False, asset=True)
        self.assertEqual(code, 1, report)
        self.assertTrue(any('docs/agents/fabian-website.md' in b for b in report['blocking']))

    def test_kerstin_and_other_actors_cannot_approve_maintenance(self):
        for actor in ('U0CE4NY7KC2', 'UOTHER', None):
            with self.subTest(actor=actor):
                self.maintenance_record['authorizer_id'] = actor
                self.assertEqual(self.maintenance_check()[0], 1)

    def test_exact_source_message_is_required(self):
        for source in (None, {},
                       dict(channel_id='OTHER', message_ts='1794230153.839529'),
                       dict(channel_id='C0CEMKENSQ1', message_ts='1794230153.839530')):
            with self.subTest(source=source):
                self.maintenance_record['source'] = source
                self.assertEqual(self.maintenance_check()[0], 1)

    def test_wrong_branch_sandbox_purpose_and_schema_are_rejected(self):
        for key, value in (('sandbox_id', 'another-update'), ('purpose', 'sandbox-review'),
                           ('purpose', 'live-publication'), ('version', True), ('extra', 'not allowed')):
            with self.subTest(key=key, value=value):
                original = self.maintenance_record.copy()
                self.maintenance_record[key] = value
                self.assertEqual(self.maintenance_check()[0], 1)
                self.maintenance_record = original
        self.git('checkout', '-qb', 'sandbox/another-update')
        self.assertEqual(self.maintenance_check()[0], 1)

    def test_wrong_missing_duplicate_and_malformed_inventory_is_rejected(self):
        original = self.maintenance_record['files']
        for files in (None, [], original[:-1], original + [original[0]],
                      original + [dict(path='docs/extra.md', sha256='0' * 64)],
                      [dict(path='../outside', sha256='0' * 64)], [None],
                      [dict(path=['not-a-path'], sha256='0' * 64)]):
            with self.subTest(files=files):
                self.maintenance_record['files'] = files
                self.assertEqual(self.maintenance_check()[0], 1)
        self.maintenance_record['files'] = original

    def test_every_file_digest_is_enforced(self):
        for item in self.maintenance_record['files']:
            with self.subTest(path=item['path']):
                original = item['sha256']
                item['sha256'] = '0' * 64
                self.assertEqual(self.maintenance_check()[0], 1)
                item['sha256'] = original

    def test_committed_and_working_bytes_must_both_match(self):
        path = 'docs/help/team-help.md'
        self.write(path, 'uncommitted new bytes')
        self.assertEqual(self.maintenance_check()[0], 1)
        item = next(i for i in self.maintenance_record['files'] if i['path'] == path)
        item['sha256'] = hashlib.sha256((self.root / path).read_bytes()).hexdigest()
        self.assertEqual(self.maintenance_check()[0], 1)  # working digest alone is insufficient
        self.git('add', path)
        self.git('commit', '-qm', 'exact revised maintenance')
        self.assertEqual(self.maintenance_check()[0], 0)

    def test_maintenance_does_not_waive_other_docs_scripts_css_or_config(self):
        for path in ('docs/extra.md', 'scripts/extra.py', CSS, '_config.yml'):
            self.write(path, 'not authorized')
        self.git('add', '-A')
        self.git('commit', '-qm', 'unrelated restricted changes')
        code, report = self.maintenance_check()
        self.assertEqual(code, 1)
        for path in ('docs/extra.md', 'scripts/extra.py', CSS, '_config.yml'):
            self.assertTrue(any(path in b for b in report['blocking']), report)

    def test_maintenance_deletions_symlinks_and_executable_modes_are_rejected(self):
        path = 'docs/help/team-help.md'
        target = self.root / path
        target.chmod(0o755)
        self.assertEqual(self.maintenance_check()[0], 1)
        target.chmod(0o644)
        target.unlink()
        target.symlink_to('team-help.pdf')
        self.assertEqual(self.maintenance_check()[0], 1)
        self.git('add', path)
        self.git('commit', '-qm', 'symlink fixture')
        self.assertEqual(self.maintenance_check()[0], 1)
        target.unlink()
        self.git('add', path)
        self.git('commit', '-qm', 'deletion fixture')
        self.assertEqual(self.maintenance_check()[0], 1)

    def test_committed_executable_cannot_be_hidden_by_working_mode(self):
        path = 'docs/help/team-help.md'
        self.git('update-index', '--chmod=+x', path)
        self.git('commit', '-qm', 'executable fixture')
        (self.root / path).chmod(0o644)
        self.assertEqual(self.maintenance_check()[0], 1)

    def test_private_record_location_permissions_and_symlinks(self):
        self.assertEqual(self.maintenance_check()[0], 0)
        self.maintenance.chmod(0o644)
        self.assertEqual(self.maintenance_check(write_record=False)[0], 1)
        self.maintenance.chmod(0o700)
        self.assertEqual(self.maintenance_check(write_record=False)[0], 1)
        original = self.maintenance.with_suffix('.original')
        self.maintenance.rename(original)
        self.maintenance.symlink_to(original)
        self.assertEqual(self.maintenance_check(write_record=False)[0], 1)
        self.maintenance = self.root / 'maintenance.json'
        self.assertEqual(self.maintenance_check()[0], 1)

    def test_separate_asset_and_maintenance_records_can_coexist(self):
        self.write(CSS, '.release-home .hero { color: navy; }')
        self.git('add', CSS)
        self.git('commit', '-qm', 'scoped styling fixture')
        code, report = self.maintenance_check(asset=True)
        self.assertEqual(code, 0, report)
        self.assertTrue(any('Scoped sandbox-review asset' in c for c in report['changes']))

    def test_wrong_record_owner_and_malformed_json_fail_closed(self):
        self.assertEqual(self.maintenance_check()[0], 0)
        import importlib.util
        from unittest.mock import patch
        import os
        spec = importlib.util.spec_from_file_location('maintenance_owner_checker', self.root / 'scripts/sandbox_check.py')
        assert spec is not None and spec.loader is not None
        checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checker)
        # Ownership is the one OS condition an unprivileged fixture cannot set.
        other_uid = os.getuid() + 1
        with patch.object(checker.os, 'getuid', return_value=other_uid):
            with self.assertRaisesRegex(ValueError, 'operator-owned'):
                checker.load_maintenance_approval(str(self.maintenance))
        self.maintenance.write_text('{bad json')
        self.assertEqual(self.maintenance_check(write_record=False)[0], 1)
        self.maintenance.write_bytes(b'\xff')
        self.assertEqual(self.maintenance_check(write_record=False)[0], 1)

    def test_wrong_deployed_url_is_rejected_without_network(self):
        self.assertEqual(self.maintenance_check()[0], 0)
        import importlib.util
        spec = importlib.util.spec_from_file_location('maintenance_checker', self.root / 'scripts/sandbox_check.py')
        assert spec is not None and spec.loader is not None
        checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checker)
        for url in ('https://forabrighterevanston.org/sandbox/other/',
                    'https://forabrighterevanston.org/',
                    'http://forabrighterevanston.org/sandbox/poll-model-release/'):
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, 'deployed URL'):
                checker.load_maintenance_approval(str(self.maintenance), url)


if __name__ == '__main__':
    unittest.main()
