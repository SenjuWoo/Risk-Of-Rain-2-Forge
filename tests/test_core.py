"""Regression tests for real package bytes and owned source operations.

Uses an isolated fixture inside artifacts/; never touches game or manager data.
"""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import shutil
import struct
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import zlib

from ror2forge import core
from ror2forge.cli import main

REAL_ROOT = core.ROOT


class CoreTests(unittest.TestCase):
    def setUp(self):
        area = REAL_ROOT / "artifacts/test-temp"
        area.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=area)
        self.root = Path(self.temp.name)
        shutil.copytree(REAL_ROOT / "templates", self.root / "templates")
        shutil.copyfile(REAL_ROOT / "NuGet.Config", self.root / "NuGet.Config")
        self.override = patch.object(core, "ROOT", self.root)
        self.override.start()

    def tearDown(self):
        self.override.stop()
        self.temp.cleanup()

    def built_fixture(self, name="Example"):
        core.new_mod(name, "Team")
        folder = core.project(name)
        dll = folder / "build/bin" / f"{name}.dll"
        dll.parent.mkdir(parents=True)
        dll.write_bytes(b"MZ" + b"fixture-dll")
        core.write_json(folder / "build/receipt.json", {"assembly_sha256": core.sha256(dll), "source_sha256": core.source_digest(folder)})
        return folder

    def archive(self, extra=None, manifest=None, icon=None):
        target = self.root / "test.zip"
        with zipfile.ZipFile(target, "w") as package:
            package.writestr("manifest.json", json.dumps(manifest or {"name": "Test", "version_number": "1.0.0", "website_url": "", "description": "Test", "dependencies": []}))
            package.writestr("README.md", "# Test\n")
            package.writestr("icon.png", core.make_icon() if icon is None else icon)
            for name, data in (extra or {}).items():
                package.writestr(name, data)
        return target

    def test_names_reject_traversal_and_devices(self):
        for name in ("../escape", "a/b", "a;whoami", "CON", "NUL", "COM1", "x" * 65):
            with self.subTest(name=name), self.assertRaises(ValueError):
                core.project(name)

    def test_owned_rejects_external_path(self):
        with self.assertRaises(ValueError):
            core.owned(self.root.parent / "elsewhere")

    def test_scaffold_refuses_overwrite(self):
        core.new_mod("Example", "Team")
        source = (core.project("Example") / "src/Plugin.cs").read_bytes()
        with self.assertRaises(ValueError):
            core.new_mod("Example", "Team")
        self.assertEqual(source, (core.project("Example") / "src/Plugin.cs").read_bytes())

    def test_keyword_namespace_is_escaped(self):
        core.new_mod("class", "Team")
        self.assertIn("namespace @class;", (core.project("class") / "src/Plugin.cs").read_text())

    def test_stats_uses_true_multiplier(self):
        core.new_mod("Stats", "Team", "stats")
        folder = core.project("Stats")
        self.assertIn("moveSpeedTotalMult *=", (folder / "src/Plugin.cs").read_text())
        self.assertIn("RiskofThunder-R2API_RecalculateStats-1.7.0", core.read_json(folder / "manifest.json")["dependencies"])

    def test_package_allowlist_and_reproducibility(self):
        folder = self.built_fixture()
        (folder / "build/secret.log").write_text("do not ship")
        one = core.package_mod("Example")
        two = core.package_mod("Example")
        self.assertEqual(one["sha256"], two["sha256"])
        self.assertEqual(set(one["files"]), {"manifest.json", "README.md", "icon.png", "plugins/Example/Example.dll"})

    def test_stale_source_prevents_package(self):
        folder = self.built_fixture()
        with (folder / "src/Plugin.cs").open("a") as stream:
            stream.write("\n// change\n")
        with self.assertRaisesRegex(ValueError, "build again"):
            core.package_mod("Example")

    def test_resource_and_ancestor_props_change_digest(self):
        folder = self.built_fixture()
        before = core.source_digest(folder)
        (folder / "src/Embedded.resx").write_text("resource")
        after = core.source_digest(folder)
        self.assertNotEqual(before, after)
        (self.root / "Directory.Build.props").write_text("<Project />")
        self.assertNotEqual(after, core.source_digest(folder))

    def test_modified_dll_prevents_package(self):
        folder = self.built_fixture()
        (folder / "build/bin/Example.dll").write_bytes(b"altered")
        with self.assertRaisesRegex(ValueError, "build again"):
            core.package_mod("Example")

    def test_version_mismatch_prevents_package(self):
        folder = self.built_fixture()
        manifest = core.read_json(folder / "manifest.json")
        manifest["version_number"] = "2.0.0"
        core.write_json(folder / "manifest.json", manifest)
        with self.assertRaisesRegex(ValueError, "must agree"):
            core.package_mod("Example")

    def test_package_accepts_literal_version_with_custom_spacing(self):
        folder = self.built_fixture()
        source = folder / "src/Plugin.cs"
        source.write_text(source.read_text().replace("PluginVersion = ", "PluginVersion="))
        core.write_json(folder / "build/receipt.json", {"assembly_sha256": core.sha256(folder / "build/bin/Example.dll"), "source_sha256": core.source_digest(folder)})
        self.assertTrue(core.package_mod("Example")["valid"])

    def test_comment_cannot_hide_wrong_plugin_version(self):
        folder = self.built_fixture()
        source = folder / "src/Plugin.cs"
        source.write_text(source.read_text().replace('PluginVersion = "1.0.0"', 'PluginVersion = "2.0.0"') + '\n// PluginVersion = "1.0.0"\n')
        with self.assertRaisesRegex(ValueError, "PluginVersion must agree"):
            core.package_mod("Example")

    def test_changed_release_cannot_replace_same_version(self):
        folder = self.built_fixture()
        core.package_mod("Example")
        (folder / "README.md").write_text("Different release")
        with self.assertRaisesRegex(ValueError, "bump"):
            core.package_mod("Example")

    def test_content_assets_are_included(self):
        folder = self.built_fixture()
        (folder / "content/testassets").write_bytes(b"asset bundle fixture")
        core.write_json(folder / "build/receipt.json", {"assembly_sha256": core.sha256(folder / "build/bin/Example.dll"), "source_sha256": core.source_digest(folder)})
        result = core.package_mod("Example")
        self.assertIn("plugins/Example/testassets", result["files"])

    def test_content_cannot_bundle_other_dlls(self):
        folder = self.built_fixture()
        (folder / "content/RoR2.dll").write_bytes(b"forbidden")
        core.write_json(folder / "build/receipt.json", {"assembly_sha256": core.sha256(folder / "build/bin/Example.dll"), "source_sha256": core.source_digest(folder)})
        with self.assertRaisesRegex(ValueError, "runtime assets"):
            core.package_mod("Example")

    def test_valid_zip(self):
        self.assertTrue(core.validate(self.archive())["valid"])

    def test_traversal_and_runtime_dll_rejected(self):
        result = core.validate(self.archive({"../evil": b"x", "plugins/RoR2.dll": b"x"}))
        self.assertFalse(result["valid"])
        self.assertTrue(any("unsafe" in item for item in result["errors"]))
        self.assertTrue(any("game assembly" in item for item in result["errors"]))

    def test_case_collision_rejected(self):
        result = core.validate(self.archive({"readme.md": b"x"}))
        self.assertFalse(result["valid"])

    def test_truncated_or_corrupt_png_rejected(self):
        icon = core.make_icon()
        self.assertFalse(core.validate(self.archive(icon=icon[:33]))["valid"])
        damaged = bytearray(icon)
        damaged[50] ^= 1
        self.assertFalse(core.check_icon(damaged))

    def test_valid_crc_with_incomplete_pixel_data_is_rejected(self):
        icon = core.make_icon()
        data = b"IDAT" + zlib.compress(b"\0")
        chunk = struct.pack(">I", len(data) - 4) + data + struct.pack(">I", zlib.crc32(data) & 0xffffffff)
        forged = icon[:33] + chunk + icon[-12:]
        self.assertFalse(core.check_icon(forged))

    def test_manifest_boundaries(self):
        manifest = {"name": "X" * 128, "version_number": "1.0.0", "description": "x" * 250, "website_url": "", "dependencies": ["Team-Package-1.0.0"]}
        self.assertEqual(core.check_manifest(manifest), [])
        for field, value in (("name", "X" * 129), ("description", "x" * 251), ("dependencies", ["bad"]), ("version_number", "1.0"), ("website_url", "file:///local")):
            self.assertTrue(core.check_manifest({**manifest, field: value}), field)

    def test_log_tail_and_candidates(self):
        log = self.root / "log.txt"
        log.write_text("first\nError: missing API\nlast\n")
        result = core.logs(str(log), 2)
        self.assertEqual(result["tail"], "Error: missing API\nlast\n")
        self.assertEqual(len(result["possible_issues"]), 1)
        with self.assertRaises(ValueError):
            core.logs(str(log), 5001)

    def test_cli_exception_is_structured(self):
        output = io.StringIO()
        with redirect_stderr(output):
            code = main(["new", "../bad", "--author", "Team"])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output.getvalue())["type"], "ValueError")

    def test_cli_invalid_archive_has_nonzero_status(self):
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["validate", str(self.archive(icon=b"bad"))])
        self.assertEqual(code, 1)
        self.assertFalse(json.loads(output.getvalue())["valid"])


if __name__ == "__main__":
    unittest.main()
