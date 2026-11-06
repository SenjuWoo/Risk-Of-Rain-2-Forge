"""Release-mode fixtures and adversarial cases for the strict verification contract."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from ror2forge import core

REAL_ROOT = core.ROOT


class ReleaseModeTests(unittest.TestCase):
    def setUp(self):
        area = REAL_ROOT / "artifacts/test-temp"
        area.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=area)
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def _project(self, version="1.2.3", changelog="# 1.2.3 — x\n"):
        (self.root / "VERSION").write_text(version + "\n", encoding="utf-8")
        if changelog is not None:
            (self.root / "CHANGELOG.md").write_text(changelog, encoding="utf-8")

    def _git(self, returncode=0, stdout="", stderr="", raises=None, head="deadbeef"):
        def fake(args, **kwargs):
            if raises:
                raise raises
            if "rev-parse" in args:
                return subprocess.CompletedProcess(args, 0, head, "")
            return subprocess.CompletedProcess(args, returncode, stdout, stderr)
        return patch.object(core.subprocess, "run", side_effect=fake)

    def _publish(self, head="deadbeef", members=None, ci=None, mutate=None):
        """A release folder shaped like a real one: a real ZIP named for the version."""
        assets = self.root / "assets"
        assets.mkdir(exist_ok=True)
        name = "Risk-of-Rain-2-Forge-1.2.3-source.zip"
        zip_path = assets / name
        with zipfile.ZipFile(zip_path, "w") as archive:
            for member, data in (members or {"Risk-of-Rain-2-Forge-1.2.3/README.md": "hello"}).items():
                archive.writestr(member, data)
        with zipfile.ZipFile(zip_path) as archive:
            entry_count = len(archive.infolist())
        receipt = {"commit": head,
                   "artifact": {"file": name, "sha256": core.sha256(zip_path),
                                "size_bytes": zip_path.stat().st_size, "files": entry_count},
                   "ci_checks": ci if ci is not None else [{"name": "CI", "conclusion": "success"}]}
        if mutate:
            receipt = mutate(receipt)
        (assets / "BUILD-RECEIPT.json").write_text(json.dumps(receipt), encoding="utf-8")
        sums = [f"{core.sha256(zip_path)}  {name}",
                f"{core.sha256(assets / 'BUILD-RECEIPT.json')}  BUILD-RECEIPT.json", ""]
        (assets / "SHA256SUMS").write_text("\n".join(sums), encoding="utf-8")
        return assets

    @staticmethod
    def _blob(data: bytes) -> str:
        return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()

    def _release(self, assets, head="deadbeef", ci=("verified", ["CI:success"]), tree=None):
        expected = tree if tree is not None else {"README.md": self._blob(b"hello")}
        # The receipt contract and the tag comparison are exercised separately: here the tag's tree is supplied,
        # so these cases isolate receipt/archive validation from Git.
        with patch.object(core, "ROOT", self.root), patch("ror2forge.__version__", "1.2.3"), \
                patch.object(core, "_ci_state", return_value=ci), \
                patch.object(core, "_git_tree", return_value=expected), \
                self._git(stdout="v1.2.3", head=head):
            return core.release_check("release", assets)

    # --- the legitimate case still passes
    def test_complete_assets_verify(self):
        self._project()
        result = self._release(self._publish())
        self.assertTrue(result["release_verified"], result["errors"])
        self.assertEqual(result["checks"], {"version": True, "tag": True, "assets": True, "ci": "verified"})

    # --- fabrications that used to pass
    def test_plain_text_masquerading_as_a_source_zip_is_rejected(self):
        self._project()
        assets = self._publish()
        name = "Risk-of-Rain-2-Forge-1.2.3-source.zip"
        (assets / name).write_bytes(b"NOT-A-ZIP")
        receipt = json.loads((assets / "BUILD-RECEIPT.json").read_text())
        receipt["artifact"]["sha256"] = core.sha256(assets / name)
        receipt["artifact"]["size_bytes"] = (assets / name).stat().st_size
        (assets / "BUILD-RECEIPT.json").write_text(json.dumps(receipt))
        sums = [f"{receipt['artifact']['sha256']}  {name}",
                f"{core.sha256(assets / 'BUILD-RECEIPT.json')}  BUILD-RECEIPT.json", ""]
        (assets / "SHA256SUMS").write_text("\n".join(sums))
        result = self._release(assets)
        self.assertFalse(result["release_verified"])
        self.assertIn("not a ZIP", " ".join(result["errors"]))

    def test_empty_receipt_object_is_rejected(self):
        self._project()
        result = self._release(self._publish(mutate=lambda _: {}))
        self.assertFalse(result["release_verified"])
        self.assertIn("non-empty JSON object", " ".join(result["errors"]))

    def test_json_array_receipt_is_rejected(self):
        self._project()
        assets = self._publish()
        (assets / "BUILD-RECEIPT.json").write_text("[]")
        result = self._release(assets)
        self.assertFalse(result["release_verified"])

    def test_failed_ci_in_receipt_is_rejected(self):
        self._project()
        result = self._release(self._publish(ci=[{"name": "CI", "conclusion": "failure"}]))
        self.assertFalse(result["release_verified"])
        self.assertIn("did not succeed", " ".join(result["errors"]))

    def test_receipt_claim_without_independent_ci_is_not_verified(self):
        self._project()
        result = self._release(self._publish(), ci=("unknown", []))
        self.assertTrue(result["valid"], result["errors"])
        self.assertFalse(result["release_verified"])
        self.assertEqual(result["checks"]["ci"], "unknown")

    def test_failed_independent_ci_is_an_error(self):
        self._project()
        result = self._release(self._publish(), ci=("failed", ["CI:failure"]))
        self.assertFalse(result["release_verified"])
        self.assertIn("independent CI", " ".join(result["errors"]))

    def test_corrupt_member_is_rejected(self):
        self._project()
        assets = self._publish()
        raw = bytearray((assets / "Risk-of-Rain-2-Forge-1.2.3-source.zip").read_bytes())
        raw[60] ^= 0xFF                      # flip a byte inside the first member's data
        (assets / "Risk-of-Rain-2-Forge-1.2.3-source.zip").write_bytes(bytes(raw))
        receipt = json.loads((assets / "BUILD-RECEIPT.json").read_text())
        receipt["artifact"]["sha256"] = core.sha256(assets / "Risk-of-Rain-2-Forge-1.2.3-source.zip")
        receipt["artifact"]["size_bytes"] = (assets / "Risk-of-Rain-2-Forge-1.2.3-source.zip").stat().st_size
        (assets / "BUILD-RECEIPT.json").write_text(json.dumps(receipt))
        sums = [f"{receipt['artifact']['sha256']}  Risk-of-Rain-2-Forge-1.2.3-source.zip",
                f"{core.sha256(assets / 'BUILD-RECEIPT.json')}  BUILD-RECEIPT.json", ""]
        (assets / "SHA256SUMS").write_text("\n".join(sums))
        result = self._release(assets)
        self.assertFalse(result["release_verified"])

    def test_unsafe_member_paths_are_rejected(self):
        self._project()
        result = self._release(self._publish(members={"../escape.txt": "x"}))
        self.assertFalse(result["release_verified"])
        self.assertIn("unsafe member path", " ".join(result["errors"]))

    def test_duplicate_members_are_rejected(self):
        self._project()
        assets = self.root / "assets"
        assets.mkdir(exist_ok=True)
        name = "Risk-of-Rain-2-Forge-1.2.3-source.zip"
        with zipfile.ZipFile(assets / name, "w") as archive:
            archive.writestr("a/README.md", "one")
            archive.writestr("a/README.md", "two")
        with zipfile.ZipFile(assets / name) as archive:
            count = len(archive.infolist())
        receipt = {"commit": "deadbeef", "artifact": {"file": name, "sha256": core.sha256(assets / name),
                   "size_bytes": (assets / name).stat().st_size, "files": count}, "ci_checks": []}
        (assets / "BUILD-RECEIPT.json").write_text(json.dumps(receipt))
        (assets / "SHA256SUMS").write_text("\n".join([
            f"{core.sha256(assets / name)}  {name}",
            f"{core.sha256(assets / 'BUILD-RECEIPT.json')}  BUILD-RECEIPT.json", ""]))
        result = self._release(assets)
        self.assertFalse(result["release_verified"])
        self.assertIn("duplicate members", " ".join(result["errors"]))

    def test_entry_count_must_match_the_receipt(self):
        self._project()
        result = self._release(self._publish(mutate=lambda r: {**r, "artifact": {**r["artifact"], "files": 99}}))
        self.assertFalse(result["release_verified"])
        self.assertIn("entries", " ".join(result["errors"]))

    def test_wrong_receipt_commit_fails(self):
        self._project()
        assets = self._publish(head="cafebabe")
        self.assertTrue(self._release(assets, head="cafebabe")["release_verified"])
        self.assertFalse(self._release(assets, head="deadbeef")["release_verified"])

    def test_release_without_assets_is_not_verified(self):
        self._project()
        with patch.object(core, "ROOT", self.root), patch("ror2forge.__version__", "1.2.3"), \
                self._git(stdout="v1.2.3"):
            result = core.release_check("release")
        self.assertFalse(result["release_verified"])
        self.assertFalse(result["checks"]["assets"])
        self.assertEqual(result["checks"]["ci"], "unknown")

    def test_release_workflows_do_not_count_against_ci_evidence(self):
        payload = json.dumps({"check_runs": [
            {"name": "Windows tests and mod builds", "status": "completed", "conclusion": "success"},
            {"name": "Download and verify published assets", "status": "in_progress", "conclusion": None},
            {"name": "Tagged release gate", "status": "queued", "conclusion": None},
        ]})
        with patch.object(core, "_repo_slug", return_value="o/r"),                 patch.object(core.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, payload, "")):
            state, names = core._ci_state("abc123")
        self.assertEqual(state, "verified")
        self.assertEqual(names, ["Windows tests and mod builds:success"])

    def test_a_required_check_failure_is_reported(self):
        payload = json.dumps({"check_runs": [
            {"name": "Windows tests and mod builds", "status": "completed", "conclusion": "failure"},
        ]})
        with patch.object(core, "_repo_slug", return_value="o/r"),                 patch.object(core.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, payload, "")):
            self.assertEqual(core._ci_state("abc123")[0], "failed")

    def test_published_bytes_must_match_the_tag(self):
        self._project()
        assets = self._publish()
        result = self._release(assets, tree={"README.md": self._blob(b"different bytes")})
        self.assertFalse(result["release_verified"])
        self.assertIn("differs from the tag", " ".join(result["errors"]))

    def test_a_file_the_tag_does_not_have_is_rejected(self):
        self._project()
        result = self._release(self._publish(), tree={})
        self.assertFalse(result["release_verified"])
        self.assertIn("the tag does not", " ".join(result["errors"]))

    def test_a_tagged_file_missing_from_the_archive_is_rejected(self):
        self._project()
        result = self._release(self._publish(), tree={"README.md": self._blob(b"hello"), "src/x.cs": "0" * 40})
        self.assertFalse(result["release_verified"])
        self.assertIn("missing from the release archive", " ".join(result["errors"]))

    def test_real_git_tree_comparison_accepts_the_tag_and_rejects_tampering(self):
        repo = self.root / "repo"
        repo.mkdir()
        run = lambda *a: subprocess.run(["git", *a], cwd=repo, capture_output=True, check=True,
                                        text=True, env={**os.environ,
                                                        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e",
                                                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e"})
        run("init", "-q")
        (repo / "a.txt").write_text("alpha" + chr(10))
        (repo / "b.txt").write_text("beta" + chr(10))
        run("add", "-A")
        run("commit", "-qm", "one")
        run("tag", "v1.0.0")
        commit = run("rev-parse", "HEAD").stdout.strip()
        archive = self.root / "kit.zip"
        subprocess.run(["git", "-c", "core.autocrlf=false", "archive", "--format=zip", "--prefix=kit/", commit,
                        "-o", str(archive)], cwd=repo, check=True)
        with patch.object(core, "ROOT", repo):
            expected = core._git_tree(commit)
            published, stray = core._archive_tree(archive, "kit/")
        self.assertEqual(stray, [])
        self.assertEqual(core._compare_tree(expected, published), [])

        tampered = self.root / "tampered.zip"
        with zipfile.ZipFile(archive) as source, zipfile.ZipFile(tampered, "w") as target:
            for member in source.infolist():
                data = source.read(member)
                if member.filename.endswith("a.txt"):
                    data = b"alpha, but rewritten" + bytes([10])
                target.writestr(member.filename, data)
        with patch.object(core, "ROOT", repo):
            published, _ = core._archive_tree(tampered, "kit/")
            problems = core._compare_tree(core._git_tree(commit), published)
        self.assertTrue(any("differs from the tag" in problem for problem in problems), problems)
