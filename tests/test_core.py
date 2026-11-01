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

    def test_flat_asset_folder_is_rejected(self):
        # The exact shape that shipped broken: DLL and assets/ both at the ZIP root. The manager empties
        # assets/ into the package root, so the plugin cannot open assets/skins.json after install.
        broken = self.archive({"GnarSurvivor.dll": b"MZ", "assets/skins.json": b"{}"})
        result = core.validate(broken)
        self.assertFalse(result["valid"])
        self.assertTrue(any("assets/" in error and "install route" in error for error in result["errors"]), result["errors"])

    def test_plugins_route_preserves_nested_assets(self):
        good = self.archive({"plugins/GnarSurvivor.dll": b"MZ", "plugins/assets/skins.json": b"{}"})
        result = core.validate(good)
        self.assertTrue(result["valid"], result["errors"])

    def test_bepinex_prefixed_route_is_accepted(self):
        good = self.archive({"BepInEx/plugins/Mod/Mod.dll": b"MZ"})
        result = core.validate(good)
        self.assertTrue(result["valid"], result["errors"])

    def test_layout_problems_names_the_folder(self):
        problems = core.layout_problems(["assets/a.json", "assets/b.json", "plugins/x.dll"])
        self.assertEqual(len(problems), 1)
        self.assertIn("assets/", problems[0])
        self.assertIn("2 files", problems[0])

    def _audit_mod(self, deps, source):
        mod = self.root / "auditmod"
        (mod / "src").mkdir(parents=True, exist_ok=True)
        (mod / "package").mkdir(parents=True, exist_ok=True)
        (mod / "src" / "Plugin.cs").write_text(source, encoding="utf-8")
        (mod / "package" / "manifest.json").write_text(json.dumps({
            "name": "AuditMod", "version_number": "1.0.0", "website_url": "", "description": "x", "dependencies": deps,
        }), encoding="utf-8")
        return mod

    def test_audit_accepts_declared_split_module(self):
        mod = self._audit_mod(["RiskofThunder-R2API_Skins-1.4.14"],
                              '[BepInDependency("com.bepis.r2api.skins")]\nclass P {}')
        result = core.audit_project(mod)
        self.assertTrue(result["valid"], result["errors"])

    def test_audit_rejects_undeclared_split_module(self):
        # The exact bug this exists for: the attribute is there, the package dependency is not, and the
        # plugin silently never loads for users.
        mod = self._audit_mod([], '[BepInDependency("com.bepis.r2api.skins")]\nclass P {}')
        result = core.audit_project(mod)
        self.assertFalse(result["valid"])
        self.assertIn("R2API_skins", result["errors"][0])

    def test_audit_rejects_undeclared_namespace_import(self):
        mod = self._audit_mod([], 'using R2API.Skins;\nclass P {}')
        result = core.audit_project(mod)
        self.assertFalse(result["valid"])
        self.assertIn("using R2API.Skins", result["errors"][0])

    def test_procedural_template_scaffolds_and_compiles_cleanly(self):
        # The point of this template is that no Unity editor is needed to ship geometry.
        result = core.new_mod("RockMod", "Team", template="procedural")
        project = Path(result["project"])
        sources = sorted(project.rglob("*.cs"))
        self.assertTrue(sources, "template produced no C# source")
        text = "".join(source.read_text(encoding="utf-8") for source in sources)
        self.assertIn("IcoSphere", text)
        self.assertIn("Mesh", text)
        self.assertNotIn("__GUID__", text)
        self.assertIn("PluginVersion", text)

    def test_unknown_template_is_rejected(self):
        with self.assertRaises(ValueError):
            core.new_mod("Bad", "Team", template="nope")

    def test_guide_topics_resolve_to_existing_docs(self):
        # The character route must stay reachable through the CLI, not only by browsing docs/.
        # setUp repoints core.ROOT at a fixture, so read the real docs explicitly.
        with patch.object(core, "ROOT", REAL_ROOT):
            for topic in ("overview", "code", "content", "assets", "networking", "debugging", "character", "audio", "extraction"):
                result = core.guide(topic)
                self.assertTrue(Path(result["path"]).is_file(), topic)
                self.assertGreater(len(result["text"]), 200, topic)
            self.assertIn("survivor", core.guide("character")["text"].lower())
            # The audio route has to name the trap, not just exist.
            audio = core.guide("audio")["text"].lower()
            self.assertIn("wwise", audio)
            self.assertIn("audioclip", audio)
            # The extraction route has to carry the measured facts, not vibes.
            extraction = core.guide("extraction")["text"].lower()
            self.assertIn("bkhd", extraction)
            self.assertIn("bindpose", extraction)
            with self.assertRaises(ValueError):
                core.guide("nope")

    def test_wwise_status_is_reported_and_pinned(self):
        # Custom sound banks need Wwise 2023.1; doctor must say so even when nothing is installed.
        status = core.wwise_status()
        self.assertEqual(status["required"], "2023.1")
        self.assertIsInstance(status["installs"], list)
        if not status["ready"]:
            self.assertIn("AUDIO.md", status["note"])

    def test_version_file_matches_package_version(self):
        # VERSION is documentation; ror2forge.__version__ is what doctor and the MCP server report.
        # They drifted during the 1.3.0 bump, so keep them locked together.
        from ror2forge import __version__

        self.assertEqual((REAL_ROOT / "VERSION").read_text(encoding="utf-8").strip(), __version__)

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
