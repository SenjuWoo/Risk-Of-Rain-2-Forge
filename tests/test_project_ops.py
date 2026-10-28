"""Version workflow checks using real owned fixture files and injected write failure."""
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from ror2forge import core, project_ops


class BumpTests(unittest.TestCase):
    def setUp(self):
        area = core.ROOT / "artifacts/test-temp"
        area.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=area)
        self.root = Path(self.temporary.name)
        shutil.copytree(core.ROOT / "templates", self.root / "templates")
        shutil.copyfile(core.ROOT / "NuGet.Config", self.root / "NuGet.Config")
        self.override = patch.object(core, "ROOT", self.root)
        self.override.start()
        core.new_mod("Example", "Team")
        self.folder = core.project("Example")

    def tearDown(self):
        self.override.stop()
        self.temporary.cleanup()

    def originals(self):
        return {str(path.relative_to(self.folder)): path.read_bytes() for path in self.folder.rglob("*") if path.is_file() and "build" not in path.relative_to(self.folder).parts}

    def test_patch_minor_major_and_explicit(self):
        for target, expected in (("patch", "1.0.1"), ("minor", "1.1.0"), ("major", "2.0.0"), ("3.4.5", "3.4.5")):
            with self.subTest(target=target):
                result = project_ops.bump("Example", target)
                self.assertEqual(result["version"], expected)
                self.assertEqual(core.read_json(self.folder / "forge.json")["version"], expected)
                self.assertEqual(core.read_json(self.folder / "manifest.json")["version_number"], expected)
                self.assertIn(f"<Version>{expected}</Version>", (self.folder / "src/Example.csproj").read_text())
                self.assertIn(f'PluginVersion = "{expected}"', (self.folder / "src/Plugin.cs").read_text())

    def test_backup_preserves_exact_originals_and_custom_values(self):
        manifest = core.read_json(self.folder / "manifest.json")
        manifest["description"] = "Custom description"
        core.write_json(self.folder / "manifest.json", manifest)
        before = self.originals()
        result = project_ops.bump("Example", "patch")
        backup = Path(result["backup"])
        for path in result["changed"]:
            self.assertEqual((backup / "original" / path).read_bytes(), before[path])
        self.assertEqual(core.read_json(self.folder / "manifest.json")["description"], "Custom description")
        self.assertEqual(core.read_json(backup / "transaction.json")["status"], "applied")

    def test_source_bom_and_line_endings_are_preserved(self):
        source = self.folder / "src/Plugin.cs"
        original = b"\xef\xbb\xbf" + source.read_bytes().replace(b"\n", b"\r\n")
        source.write_bytes(original)
        project_ops.bump("Example", "patch")
        self.assertEqual(source.read_bytes(), original.replace(b'PluginVersion = "1.0.0"', b'PluginVersion = "1.0.1"'))

    def test_state_and_changelog_preserve_custom_notes(self):
        with (self.folder / "STATE.md").open("a") as stream:
            stream.write("\nCustom note: keep this.\n")
        project_ops.bump("Example", "patch")
        self.assertIn("Custom note: keep this.", (self.folder / "STATE.md").read_text())
        self.assertIn("Version: 1.0.1", (self.folder / "STATE.md").read_text())
        self.assertIn("# 1.0.0", (self.folder / "CHANGELOG.md").read_text())

    def test_invalid_or_older_version_makes_no_changes(self):
        before = self.originals()
        for target in ("1.0.0", "0.9.9", "1.0", "01.2.3", "../evil", "1.2.3-beta"):
            with self.subTest(target=target), self.assertRaises(ValueError):
                project_ops.bump("Example", target)
            self.assertEqual(self.originals(), before)
        self.assertFalse((self.folder / "build").exists())

    def test_inconsistent_manifest_makes_no_changes(self):
        metadata = core.read_json(self.folder / "manifest.json")
        metadata["version_number"] = "2.0.0"
        core.write_json(self.folder / "manifest.json", metadata)
        before = self.originals()
        with self.assertRaisesRegex(ValueError, "must agree"):
            project_ops.bump("Example", "patch")
        self.assertEqual(self.originals(), before)

    def test_duplicate_constant_is_rejected(self):
        source = self.folder / "src/Plugin.cs"
        source.write_text(source.read_text() + '\nclass Other { public const string PluginVersion = "1.0.0"; }\n')
        before = self.originals()
        with self.assertRaisesRegex(ValueError, "one literal"):
            project_ops.bump("Example", "patch")
        self.assertEqual(self.originals(), before)

    def test_comments_and_strings_are_not_version_declarations(self):
        source = self.folder / "src/Plugin.cs"
        source.write_text(source.read_text() + '\n/*\npublic const string PluginVersion = "9.0.0";\n*/\n// public const string PluginVersion = "9.0.0";\n')
        project_ops.bump("Example", "patch")
        self.assertIn('public const string PluginVersion = "9.0.0";', source.read_text())
        declaration = core.plugin_version_declaration('string text = "const string PluginVersion = \\"9.0.0\\";"; const string PluginVersion = "1.0.0";')
        self.assertEqual(declaration.group("version"), "1.0.0")

    def test_xml_comment_decoy_is_preserved(self):
        path = self.folder / "src/Example.csproj"
        path.write_text(path.read_text().replace("<PropertyGroup>", "<PropertyGroup>\n<!-- <Version>8.0.0</Version> -->"))
        project_ops.bump("Example", "patch")
        self.assertIn("<!-- <Version>8.0.0</Version> -->", path.read_text())

    def test_conditional_xml_requires_manual_edit(self):
        path = self.folder / "src/Example.csproj"
        path.write_text(path.read_text().replace("<Version>", '<Version Condition="true">'))
        before = self.originals()
        with self.assertRaisesRegex(ValueError, "manual edit"):
            project_ops.bump("Example", "patch")
        self.assertEqual(self.originals(), before)

    def test_write_failure_rolls_back_all_changed_files(self):
        before = self.originals()
        original_replace = project_ops.os.replace
        calls = 0
        def fail_third(source, destination):
            nonlocal calls
            calls += 1
            if calls == 3:
                raise OSError("injected write failure")
            return original_replace(source, destination)
        with patch.object(project_ops.os, "replace", side_effect=fail_third):
            with self.assertRaisesRegex(OSError, "injected"):
                project_ops.bump("Example", "patch")
        self.assertEqual(self.originals(), before)
        self.assertTrue(list((self.folder / "build/version-backups").glob("*/original/forge.json")))

    def test_final_receipt_failure_also_rolls_back(self):
        before = self.originals()
        write_json = core.write_json
        def fail_applied(path, value):
            if value.get("status") == "applied":
                raise OSError("receipt write failed")
            return write_json(path, value)
        with patch.object(core, "write_json", side_effect=fail_applied):
            with self.assertRaisesRegex(OSError, "receipt write failed"):
                project_ops.bump("Example", "patch")
        self.assertEqual(self.originals(), before)

    def test_bump_invalidates_build_without_deleting_old_artifacts(self):
        output = self.folder / "build/bin/Example.dll"
        output.parent.mkdir(parents=True)
        output.write_bytes(b"MZfixture")
        core.write_json(self.folder / "build/receipt.json", {"assembly_sha256": core.sha256(output), "source_sha256": core.source_digest(self.folder)})
        old_package = core.package_mod("Example")
        old_bytes = Path(old_package["archive"]).read_bytes()
        project_ops.bump("Example", "patch")
        with self.assertRaisesRegex(ValueError, "build again"):
            core.package_mod("Example")
        self.assertEqual(Path(old_package["archive"]).read_bytes(), old_bytes)
        self.assertTrue((self.folder / "build/receipt.json").is_file())

    def test_custom_state_format_is_not_destroyed(self):
        state = self.folder / "STATE.md"
        state.write_text("# Human notes\nCurrent release is 1.0.0\n")
        result = project_ops.bump("Example", "patch")
        self.assertTrue(result["warnings"])
        self.assertEqual(state.read_text(), "# Human notes\nCurrent release is 1.0.0\n")

    def test_unsupported_raw_strings_are_refused_without_writes(self):
        source = self.folder / "src/Plugin.cs"
        source.write_text(source.read_text() + '\n// raw marker: """\n')
        before = self.originals()
        with self.assertRaisesRegex(ValueError, "Raw C# strings"):
            project_ops.bump("Example", "patch")
        self.assertEqual(self.originals(), before)


if __name__ == "__main__":
    unittest.main()
