"""Security regressions from the v1.13.2 audit: project isolation, package snapshots, log access."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from ror2forge import core, safefs

REAL_ROOT = core.ROOT


def make_link(src: Path, dst: Path) -> bool:
    """Create a file or directory link; junction fallback keeps Windows covered without admin rights."""
    try:
        os.symlink(src, dst, target_is_directory=src.is_dir())
        return True
    except (OSError, NotImplementedError):
        if src.is_dir() and os.name == "nt":
            result = subprocess.run(["cmd", "/c", "mklink", "/J", str(dst), str(src)],
                                    capture_output=True, text=True)
            return result.returncode == 0
        return False


class IsolationTests(unittest.TestCase):
    def setUp(self):
        area = REAL_ROOT / "artifacts/test-temp"
        area.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=area)
        self.root = Path(self.temp.name)
        shutil.copytree(REAL_ROOT / "templates", self.root / "templates")
        shutil.copyfile(REAL_ROOT / "NuGet.Config", self.root / "NuGet.Config")
        self.patch = patch.object(core, "ROOT", self.root)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def _project(self, name="Victim"):
        core.new_mod(name, "Team")
        folder = core.project(name)
        dll = folder / "build/bin" / f"{name}.dll"
        dll.parent.mkdir(parents=True, exist_ok=True)
        dll.write_bytes(b"MZ" + b"victim-dll")
        self._receipt(folder)
        return folder

    def _receipt(self, folder):
        """Fresh receipt for the current tree; call it after building links so packaging reaches validation."""
        dll = folder / "build/bin" / f"{folder.name}.dll"
        core.write_json(folder / "build/receipt.json", {
            "assembly_sha256": core.sha256(dll),
            "source_sha256": core.source_digest(folder),
            "package_sha256": core.package_digest(folder),
        })

    def test_cross_project_file_link_is_rejected(self):
        other = self._project("Other")
        (other / "PRIVATE-do-not-ship.txt").write_text("secret", encoding="utf-8")
        victim = self._project()
        (victim / "content").mkdir(exist_ok=True)
        link = victim / "content/asset.txt"
        if not make_link(other / "PRIVATE-do-not-ship.txt", link):
            self.skipTest("this platform cannot create file links")
        self._receipt(victim)
        with self.assertRaises(ValueError) as raised:
            core.package_mod("Victim")
        self.assertIn("links or junctions", str(raised.exception))
        self.assertFalse((self.root / "artifacts/Team-Victim-1.0.0.zip").exists())

    def test_cross_project_directory_link_is_rejected(self):
        other = self._project("Other")
        (other / "private").mkdir()
        (other / "private" / "secret.txt").write_text("secret", encoding="utf-8")
        victim = self._project()
        link = victim / "content"
        if not make_link(other / "private", link):
            self.skipTest("this platform cannot create directory links")
        self._receipt(victim)
        with self.assertRaises(ValueError) as raised:
            core.package_mod("Victim")
        self.assertIn("links or junctions", str(raised.exception))

    def test_link_escaping_the_forge_root_is_rejected(self):
        victim = self._project()
        (victim / "content").mkdir(exist_ok=True)
        outside = Path(tempfile.mkdtemp()) / "outside.txt"
        outside.write_text("outside", encoding="utf-8")
        link = victim / "content/escape.txt"
        if not make_link(outside, link):
            self.skipTest("this platform cannot create file links")
        self._receipt(victim)
        with self.assertRaises(ValueError) as raised:
            core.package_mod("Victim")
        self.assertIn("links or junctions", str(raised.exception))

    def test_normal_nested_assets_still_package(self):
        victim = self._project()
        (victim / "content/assets/deep").mkdir(parents=True)
        (victim / "content/assets/deep/skin.json").write_text("{}", encoding="utf-8")
        core.write_json(victim / "build/receipt.json", {
            "assembly_sha256": core.sha256(victim / "build/bin/Victim.dll"),
            "source_sha256": core.source_digest(victim),
            "package_sha256": core.package_digest(victim),
        })
        result = core.package_mod("Victim")
        self.assertTrue(result["valid"])
        with zipfile.ZipFile(result["archive"]) as archive:
            self.assertIn("plugins/Victim/assets/deep/skin.json", archive.namelist())

    def test_plain_traversal_into_another_project_is_rejected(self):
        other = self._project("Other")
        victim = self._project()
        with self.assertRaises(ValueError) as raised:
            core.project_input(victim, victim / "content" / ".." / ".." / "Other" / "PRIVATE.txt")
        self.assertIn("escapes its project", str(raised.exception))

    def test_reparse_points_are_rejected_even_without_link_privileges(self):
        victim = self._project()
        (victim / "content").mkdir(exist_ok=True)
        with patch.object(core, "_reparse_point", side_effect=lambda p: p == (victim / "content").absolute()):
            with self.assertRaises(ValueError) as raised:
                core.project_input(victim, victim / "content" / "asset.txt")
        self.assertIn("links or junctions", str(raised.exception))

    def test_cross_project_hardlink_is_rejected(self):
        other = self._project("Other")
        (other / "PRIVATE-do-not-ship.txt").write_text("secret", encoding="utf-8")
        victim = self._project()
        (victim / "content").mkdir(exist_ok=True)
        link = victim / "content/asset.txt"
        try:
            os.link(other / "PRIVATE-do-not-ship.txt", link)
        except (OSError, NotImplementedError):
            self.skipTest("this platform cannot create hard links")
        self._receipt(victim)
        with self.assertRaises(ValueError) as raised:
            core.package_mod("Victim")
        self.assertIn("multiple hard links", str(raised.exception))

    def test_file_swapped_after_validation_is_never_read(self):
        other = self._project("Other")
        (other / "PRIVATE-do-not-ship.txt").write_text("secret", encoding="utf-8")
        victim = self._project()
        (victim / "content").mkdir(exist_ok=True)
        asset = victim / "content/asset.txt"
        asset.write_text("mine", encoding="utf-8")
        self._receipt(victim)
        real = core.project_input

        def swap_after_validation(folder, path):
            resolved = real(folder, path)
            if resolved == asset.resolve():
                resolved.unlink()
                make_link(other / "PRIVATE-do-not-ship.txt", resolved)
            return resolved

        with patch.object(core, "project_input", side_effect=swap_after_validation):
            with self.assertRaises(ValueError):
                core.package_mod("Victim")

    def test_packaging_quota_is_enforced_before_reading(self):
        victim = self._project()
        (victim / "content").mkdir(exist_ok=True)
        big = victim / "content/huge.bin"
        with big.open("wb") as handle:
            handle.truncate(1024)
        self._receipt(victim)
        with patch.object(core, "Budget", lambda *a, **k: safefs.Budget(files=10, total=10, per_file=10)):
            with self.assertRaises(ValueError) as raised:
                core.package_mod("Victim")
        self.assertIn("per-file limit", str(raised.exception))

    def test_lockfile_without_provenance_is_refused(self):
        victim = self._project()
        (victim / "src" / "packages.lock.json").write_text("{}", encoding="utf-8")
        core.write_json(victim / "build/receipt.json", {
            "assembly_sha256": core.sha256(victim / "build/bin/Victim.dll"),
            "source_sha256": core.source_digest(victim),
            "package_sha256": core.package_digest(victim),
        })
        with self.assertRaises(ValueError) as raised:
            core.package_mod("Victim")
        self.assertIn("no lock provenance", str(raised.exception))


class PackageSnapshotTests(unittest.TestCase):
    def setUp(self):
        area = REAL_ROOT / "artifacts/test-temp"
        area.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=area)
        self.root = Path(self.temp.name)
        shutil.copytree(REAL_ROOT / "templates", self.root / "templates")
        shutil.copyfile(REAL_ROOT / "NuGet.Config", self.root / "NuGet.Config")
        self.patch = patch.object(core, "ROOT", self.root)
        self.patch.start()
        core.new_mod("Snap", "Team")
        self.folder = core.project("Snap")
        self.dll = self.folder / "build/bin/Snap.dll"
        self.dll.parent.mkdir(parents=True, exist_ok=True)
        self.dll.write_bytes(b"MZ" + b"original")
        core.write_json(self.folder / "build/receipt.json", {
            "assembly_sha256": core.sha256(self.dll),
            "source_sha256": core.source_digest(self.folder),
            "package_sha256": core.package_digest(self.folder),
        })

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def test_dll_replaced_after_the_receipt_check_cannot_enter_the_zip(self):
        original = zipfile.ZipFile.writestr
        state = {"swapped": False}

        def swapping(archive, entry, data, *args, **kwargs):
            if not state["swapped"]:
                state["swapped"] = True
                self.dll.write_bytes(b"MZ" + b"evil")
            return original(archive, entry, data, *args, **kwargs)

        with patch.object(zipfile.ZipFile, "writestr", swapping):
            result = core.package_mod("Snap")
        with zipfile.ZipFile(result["archive"]) as archive:
            self.assertEqual(archive.read("plugins/Snap/Snap.dll"), b"MZ" + b"original")

    def test_dll_changed_before_packaging_is_refused(self):
        self.dll.write_bytes(b"MZ" + b"guided")
        with self.assertRaises(ValueError):
            core.package_mod("Snap")

    def test_content_changed_during_packaging_is_refused(self):
        (self.folder / "content").mkdir(exist_ok=True)
        asset = self.folder / "content/late.txt"
        asset.write_text("one", encoding="utf-8")
        core.write_json(self.folder / "build/receipt.json", {
            "assembly_sha256": core.sha256(self.dll),
            "source_sha256": core.source_digest(self.folder),
            "package_sha256": core.package_digest(self.folder),
        })
        original = zipfile.ZipFile.writestr
        state = {"done": False}

        def mutating(archive, entry, data, *args, **kwargs):
            if not state["done"]:
                state["done"] = True
                asset.write_text("two", encoding="utf-8")
            return original(archive, entry, data, *args, **kwargs)

        with patch.object(zipfile.ZipFile, "writestr", mutating):
            with self.assertRaises(ValueError):
                core.package_mod("Snap")

    def test_unchanged_inputs_package_identically(self):
        first = core.package_mod("Snap")
        second = core.package_mod("Snap")
        self.assertEqual(first["sha256"], second["sha256"])


class LogAccessTests(unittest.TestCase):
    def setUp(self):
        area = REAL_ROOT / "artifacts/test-temp"
        area.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=area)
        self.root = Path(self.temp.name)
        self.patch = patch.object(core, "ROOT", self.root)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def test_repository_files_are_not_logs(self):
        secret = self.root / "VERSION"
        secret.write_text("9.9.9", encoding="utf-8")
        with self.assertRaises(ValueError):
            core.logs(str(secret), 5)

    def test_forge_logs_are_allowed(self):
        (self.root / "artifacts").mkdir()
        log = self.root / "artifacts/run.log"
        log.write_text("line one" + chr(10) + "Exception: boom" + chr(10), encoding="utf-8")
        result = core.logs(str(log), 10)
        self.assertEqual(len(result["possible_issues"]), 1)

    def test_oversized_log_is_refused(self):
        (self.root / "artifacts").mkdir()
        log = self.root / "artifacts/huge.log"
        with log.open("wb") as handle:
            handle.truncate(65 * 1024 * 1024)
        with self.assertRaises(ValueError):
            core.logs(str(log), 10)
