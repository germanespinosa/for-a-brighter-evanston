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


POLL_SCRIPT = 'assets/js/poll-copy.js'
POLL_DIGEST = 'e1ea7d637919e39bd28e4d67ccd7091a804832ab3658114695d504ebc7444d32'
POLL_PAGES = ['home/voter-poll/index.html', 'es/encuesta/index.html']
POLL_ROUTES = ['/home/voter-poll/', '/es/encuesta/']


class PollCopyApprovalTests(ApprovalFixture):
    def setUp(self):
        super().setUp()
        self.write('_layouts/default.html', '{{ content }}')
        for path, lang in zip(POLL_PAGES, ('en', 'es')):
            self.write(path, '---\nlayout: default\nlang: ' + lang + '\ntitle: Poll\ndescription: Poll description\n---\n<p>Poll</p>')
        self.git('add', '-A')
        self.git('commit', '-qm', 'existing poll pages')
        self.git('tag', '-f', 'baseline')
        target = self.root / POLL_SCRIPT
        target.parent.mkdir(parents=True)
        # Use the reviewed checkout bytes, never synthetic code with an invented hash.
        target.write_bytes((CHECKER.parent.parent / POLL_SCRIPT).read_bytes())
        self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(), POLL_DIGEST)
        for path in POLL_PAGES:
            page = self.root / path
            page.write_text(page.read_text().replace('layout: default', 'layout: default\nscripts: [poll-copy.js]'))
        self.git('add', '-A')
        self.git('commit', '-qm', 'reviewed clipboard feature')
        self.poll_record: dict = dict(version=1, purpose='poll-copy-sandbox', sandbox_id='poll-model-release',
                                authorizer_id='U0CE2G08ZRC',
                                source=dict(channel_id='C0CEMKENSQ1', message_ts='1794242873.127109'),
                                script=dict(path=POLL_SCRIPT, sha256=POLL_DIGEST),
                                pages=POLL_PAGES.copy(), routes=POLL_ROUTES.copy())
        self.poll_approval = Path(self.temp.name) / 'poll-copy.json'

    def poll_check(self, record=True, write_record=True):
        argv = [sys.executable, str(self.root / 'scripts/sandbox_check.py'), '--base', 'baseline', '--json']
        if record:
            if write_record:
                self.poll_approval.write_text(json.dumps(self.poll_record))
                self.poll_approval.chmod(0o600)
            argv += ['--poll-copy-approval-file', str(self.poll_approval)]
        result = subprocess.run(argv, capture_output=True, text=True)
        self.assertEqual(result.stderr, '')
        return result.returncode, json.loads(result.stdout)

    def test_exact_german_clipboard_feature_is_allowed(self):
        code, report = self.poll_check()
        self.assertEqual(code, 0, report)
        self.assertTrue(any('poll-copy-sandbox' in n for n in report['notes']))


    def test_missing_approval_keeps_script_and_loaders_blocked(self):
        code, report = self.poll_check(record=False)
        self.assertEqual(code, 1)
        self.assertTrue(any(POLL_SCRIPT in b for b in report['blocking']))
        for page in POLL_PAGES:
            self.assertTrue(any(page in b and 'scripts' in b for b in report['blocking']))

    def test_exact_schema_actor_source_paths_and_digest_are_required(self):
        original = json.loads(json.dumps(self.poll_record))
        mutations = [
            ('authorizer_id', 'U0CE4NY7KC2'), ('authorizer_id', 'German'),
            ('authorizer_id', 'UOTHER'), ('version', True), ('version', '1'),
            ('purpose', 'sandbox-review'), ('purpose', 'live-publication'),
            ('sandbox_id', 'other'), ('extra', True),
            ('source', None), ('source', {}),
            ('source', dict(channel_id='OTHER', message_ts='1794242873.127109')),
            ('source', dict(channel_id='C0CEMKENSQ1', message_ts='1794230153.839529')),
            ('source', dict(channel_id='C0CEMKENSQ1', message_ts='1794242873.127109', extra=True)),
            ('script', dict(path='assets/js/other.js', sha256=POLL_DIGEST)),
            ('script', dict(path='../poll-copy.js', sha256=POLL_DIGEST)),
            ('script', dict(path=POLL_SCRIPT, sha256='0' * 64)),
            ('script', dict(path=POLL_SCRIPT, sha256=POLL_DIGEST, extra=True)),
            ('pages', POLL_PAGES + [POLL_PAGES[0]]), ('pages', POLL_PAGES[::-1]),
            ('pages', ['foreign/index.html']), ('routes', ['/foreign/']),
        ]
        for key, value in mutations:
            with self.subTest(key=key, value=value):
                self.poll_record = dict(original, **{key: value})
                code, report = self.poll_check()
                self.assertEqual(code, 1, report)
                self.assertTrue(any('Invalid poll-copy approval' in b for b in report['blocking']))
        for key in original:
            with self.subTest(missing=key):
                self.poll_record = original.copy()
                del self.poll_record[key]
                self.assertEqual(self.poll_check()[0], 1)

    def test_duplicate_fields_and_malformed_records_are_rejected(self):
        self.assertEqual(self.poll_check()[0], 0)
        valid = json.dumps(self.poll_record)
        for content in ('{bad', '[]', valid.replace('"version": 1', '"version": 1, "version": 1'),
                        valid.replace('"path":', '"path": "ignored", "path":'),
                        valid.replace('"channel_id":', '"channel_id": "ignored", "channel_id":')):
            with self.subTest(content=content):
                self.poll_approval.write_text(content)
                self.assertEqual(self.poll_check(write_record=False)[0], 1)
        self.poll_approval.write_bytes(b'\xff')
        self.assertEqual(self.poll_check(write_record=False)[0], 1)

    def test_wrong_branch_is_rejected(self):
        self.git('checkout', '-qb', 'sandbox/other')
        self.assertEqual(self.poll_check()[0], 1)

    def test_working_and_head_script_drift_cannot_mint_a_new_digest(self):
        target = self.root / POLL_SCRIPT
        approved = target.read_bytes()
        target.write_bytes(approved + b'\n// unreviewed\n')
        self.assertEqual(self.poll_check()[0], 1)
        self.git('add', POLL_SCRIPT)
        self.git('commit', '-qm', 'unreviewed script')
        target.write_bytes(approved)
        self.assertEqual(self.poll_check()[0], 1)  # working-only restoration cannot hide HEAD drift
        self.poll_record['script']['sha256'] = hashlib.sha256(approved + b'\n// unreviewed\n').hexdigest()
        self.assertEqual(self.poll_check()[0], 1)

    def test_script_working_and_committed_modes_symlinks_and_deletion(self):
        target = self.root / POLL_SCRIPT
        approved = target.read_bytes()
        target.chmod(0o755)
        self.assertEqual(self.poll_check()[0], 1)
        self.git('add', POLL_SCRIPT)
        self.git('commit', '-qm', 'executable script')
        target.chmod(0o644)
        self.assertEqual(self.poll_check()[0], 1)
        self.git('add', POLL_SCRIPT)
        self.git('commit', '-qm', 'regular script')
        other = Path(self.temp.name) / 'script.js'
        other.write_bytes(approved)
        target.unlink()
        target.symlink_to(other)
        self.assertEqual(self.poll_check()[0], 1)
        self.git('add', POLL_SCRIPT)
        self.git('commit', '-qm', 'symlink script')
        target.unlink()
        target.write_bytes(approved)
        self.assertEqual(self.poll_check()[0], 1)
        target.unlink()
        self.git('add', POLL_SCRIPT)
        self.git('commit', '-qm', 'deleted script')
        self.assertEqual(self.poll_check()[0], 1)

    def test_private_record_permissions_location_symlinks_and_regular_file(self):
        self.assertEqual(self.poll_check()[0], 0)
        for mode in (0o644, 0o400, 0o700, 0o000):
            with self.subTest(mode=mode):
                self.poll_approval.chmod(mode)
                self.assertEqual(self.poll_check(write_record=False)[0], 1)
        self.poll_approval.chmod(0o600)
        original = self.poll_approval.with_suffix('.original')
        self.poll_approval.rename(original)
        self.poll_approval.symlink_to(original)
        self.assertEqual(self.poll_check(write_record=False)[0], 1)
        self.poll_approval.unlink()
        self.poll_approval.mkdir(mode=0o600)
        self.assertEqual(self.poll_check(write_record=False)[0], 1)
        self.poll_approval = self.root / 'private.json'
        self.assertEqual(self.poll_check()[0], 1)

    def test_wrong_owner_and_exact_optional_deployed_url(self):
        self.assertEqual(self.poll_check()[0], 0)
        import importlib.util
        import os
        from unittest.mock import patch
        spec = importlib.util.spec_from_file_location('poll_copy_checker', self.root / 'scripts/sandbox_check.py')
        assert spec is not None and spec.loader is not None
        checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checker)
        with patch.object(checker.os, 'getuid', return_value=os.getuid() + 1):
            with self.assertRaisesRegex(ValueError, 'operator-owned'):
                checker.load_poll_copy_approval(self.poll_approval)
        for suffix in ('', '/'):
            self.assertTrue(checker.load_poll_copy_approval(self.poll_approval,
                'https://forabrighterevanston.org/sandbox/poll-model-release' + suffix))
        for url in ('https://forabrighterevanston.org/',
                    'http://forabrighterevanston.org/sandbox/poll-model-release/',
                    'https://evil.invalid/sandbox/poll-model-release/',
                    'https://forabrighterevanston.org/sandbox/other/',
                    'https://forabrighterevanston.org/sandbox/poll-model-release/?x=1',
                    'https://forabrighterevanston.org/sandbox/poll-model-release/#x'):
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, 'deployed URL'):
                checker.load_poll_copy_approval(self.poll_approval, url)

    def test_base_executable_mode_change_is_not_authorized(self):
        # Even restoration to 100644 cannot waive a mode change from live.
        self.git('update-index', '--chmod=+x', POLL_SCRIPT)
        self.git('commit', '-qm', 'executable baseline')
        self.git('tag', '-f', 'baseline')
        self.git('update-index', '--chmod=-x', POLL_SCRIPT)
        self.git('commit', '-qm', 'regular mode restoration')
        code, report = self.poll_check()
        self.assertEqual(code, 1, report)
        self.assertTrue(any('mode changes' in b for b in report['blocking']))

    def test_approval_cannot_replace_an_existing_foreign_loader(self):
        target = self.root / POLL_PAGES[0]
        approved = target.read_text()
        target.write_text(approved.replace('[poll-copy.js]', '[other.js]'))
        self.git('add', '-A')
        self.git('commit', '-qm', 'other loader baseline')
        self.git('tag', '-f', 'baseline')
        target.write_text(approved)
        self.git('add', '-A')
        self.git('commit', '-qm', 'replace other loader')
        code, report = self.poll_check()
        self.assertEqual(code, 1, report)
        self.assertTrue(any('scripts' in b for b in report['blocking']))

    def test_symlink_parents_and_fifo_records_are_rejected(self):
        import os
        self.assertEqual(self.poll_check()[0], 0)
        link = Path(self.temp.name) / 'linked-dir'
        link.symlink_to(self.temp.name, target_is_directory=True)
        self.poll_approval = link / 'poll-copy.json'
        self.assertEqual(self.poll_check(write_record=False)[0], 1)
        self.poll_approval = Path(self.temp.name) / 'fifo'
        os.mkfifo(self.poll_approval, 0o600)
        self.assertEqual(self.poll_check(write_record=False)[0], 1)

    def test_extra_script_and_other_structural_settings_stay_blocked(self):
        target = self.root / POLL_PAGES[0]
        original = target.read_text()
        for replacement in ('scripts: [poll-copy.js, evil.js]', 'scripts: [evil.js]',
                            'scripts: [poll-copy.js]\ncss: [evil.css]',
                            'scripts: [poll-copy.js]\nnav: false',
                            'scripts: [poll-copy.js]\nis_home: true',
                            'scripts: [poll-copy.js]\npermalink: /foreign/'):
            with self.subTest(replacement=replacement):
                target.write_text(original.replace('scripts: [poll-copy.js]', replacement))
                self.assertEqual(self.poll_check()[0], 1)

    def test_foreign_page_cannot_load_reviewed_script(self):
        self.write('foreign/index.html', '---\nlayout: default\nlang: en\ntitle: Foreign\ndescription: Foreign page\n---\n<p>Other</p>')
        self.git('add', '-A')
        self.git('commit', '-qm', 'existing foreign page')
        self.git('tag', '-f', 'baseline')
        target = self.root / 'foreign/index.html'
        target.write_text(target.read_text().replace('layout: default', 'layout: default\nscripts: [poll-copy.js]'))
        self.git('add', '-A')
        self.git('commit', '-qm', 'foreign loader')
        code, report = self.poll_check()
        self.assertEqual(code, 1)
        self.assertTrue(any('foreign/index.html' in b and 'scripts' in b for b in report['blocking']))

    def test_unsafe_html_other_js_css_docs_and_build_stay_blocked(self):
        restricted = ('assets/js/evil.js', 'assets/css/evil.css', 'docs/extra.md', '_config.yml', '.github/workflows/build.yml')
        for path in restricted:
            self.write(path, 'unapproved')
        target = self.root / POLL_PAGES[0]
        target.write_text(target.read_text() + '<script>alert(1)</script>')
        self.git('add', '-A')
        self.git('commit', '-qm', 'restricted changes')
        code, report = self.poll_check()
        self.assertEqual(code, 1)
        for path in restricted:
            self.assertTrue(any(path in b for b in report['blocking']), report)
        self.assertTrue(any('script> tag' in b for b in report['blocking']), report)


class PollCopyMaintenanceTests(MaintenanceApprovalTests):
    def setUp(self):
        super().setUp()
        self.maintenance_record['purpose'] = 'poll-copy-maintenance'
        self.maintenance_record['source']['message_ts'] = '1794242873.127109'

    def test_new_purpose_cannot_relabel_original_permission(self):
        self.maintenance_record['source']['message_ts'] = '1794230153.839529'
        self.assertEqual(self.maintenance_check()[0], 1)
        self.maintenance_record['purpose'] = 'delegation-maintenance'
        self.maintenance_record['source']['message_ts'] = '1794242873.127109'
        self.assertEqual(self.maintenance_check()[0], 1)


if __name__ == '__main__':
    unittest.main()
