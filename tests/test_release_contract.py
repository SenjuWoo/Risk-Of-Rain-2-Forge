"""Release-mode fixtures and adversarial cases for the strict verification contract."""
import io
import json
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

    def _release(self, assets, head="deadbeef", ci=("verified", ["CI:success"])):
        with patch.object(core, "ROOT", self.root), patch("ror2forge.__version__", "1.2.3"), \
                patch.object(core, "_ci_state", return_value=ci), self._git(stdout="v1.2.3", head=head):
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
