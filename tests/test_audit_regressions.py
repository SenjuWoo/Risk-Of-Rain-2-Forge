"""Regression tests for the audit and packaging defects found in the 1.12.2 review.

Each test names the failure it exists to catch, so a future change that reintroduces the
bug fails here instead of shipping.
"""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ror2forge import core

REAL_ROOT = core.ROOT


class AuditRegressionTests(unittest.TestCase):
    def setUp(self):
        area = REAL_ROOT / "artifacts/test-temp"
        area.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=area)
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def _mod(self, files: dict[str, str], deps: list[str] | None = None) -> Path:
        mod = self.root / "mod"
        (mod / "src").mkdir(parents=True, exist_ok=True)
        (mod / "package").mkdir(parents=True, exist_ok=True)
        (mod / "package" / "manifest.json").write_text(json.dumps({
            "name": "AuditMod", "version_number": "1.0.0", "website_url": "",
            "description": "x", "dependencies": deps or [],
        }), encoding="utf-8")
        for name, text in files.items():
            (mod / "src" / name).write_text(text, encoding="utf-8")
        return mod

    # --- the exact reported false negative: `global using R2API.Skins;` with no dependency
    def test_global_using_needs_its_dependency(self):
        mod = self._mod({"Global.cs": "global using R2API.Skins;\nclass P {}"})
        result = core.audit_project(mod)
        self.assertFalse(result["valid"], "a global using was accepted without its R2API module")
        self.assertIn("Skins", result["errors"][0])

    def test_aliased_and_static_usings_are_detected(self):
        for text in ("using S = R2API.Skins.SkinDef;\nclass P {}",
                     "using static R2API.Skins.SkinCatalog;\nclass P {}"):
            with self.subTest(source=text):
                mod = self._mod({"Alias.cs": text})
                self.assertFalse(core.audit_project(mod)["valid"])

    def test_fully_qualified_reference_is_detected(self):
        mod = self._mod({"Qualified.cs": "class P { R2API.Skins.SkinDef d; }"})
        self.assertFalse(core.audit_project(mod)["valid"])

    # --- the mirror-image false positive: a commented-out using is not a dependency
    def test_commented_using_is_not_a_dependency(self):
        mod = self._mod({"Comments.cs": "// using R2API.Skins;\n/* using R2API.Items; */\nclass P {}"})
        result = core.audit_project(mod)
        self.assertTrue(result["valid"], result["errors"])
        self.assertEqual(result["r2api_modules"], [])

    # --- survivor warnings must read code, not prose
    def test_item_display_warning_survives_a_comment(self):
        source = "class P { // itemDisplayRuleSet is set elsewhere, honest\n void A(){ AddSurvivorDef(d); } }"
        mod = self._mod({"Survivor.cs": source})
        warnings = core.audit_project(mod)["warnings"]
        self.assertTrue(any("itemDisplayRuleSet" in w for w in warnings),
                        "a comment mentioning itemDisplayRuleSet suppressed a real warning")

    def test_item_display_warning_clears_when_actually_set(self):
        source = "class P { void A(){ AddSurvivorDef(d); model.itemDisplayRuleSet = rules; } }"
        mod = self._mod({"Survivor.cs": source})
        self.assertFalse(any("itemDisplayRuleSet" in w for w in core.audit_project(mod)["warnings"]))

    # --- an unrelated file must not satisfy a per-file check
    def test_other_files_apply_call_does_not_mask_loadimage_warning(self):
        mod = self._mod({
            "Texture.cs": "class T { void L(){ tex.LoadImage(bytes, false); } }",
            "Other.cs": "class O { void A(){ other.Apply(false, true); } }",
        })
        warnings = core.audit_project(mod)["warnings"]
        self.assertTrue(any("LoadImage" in w for w in warnings),
                        "an Apply(false, true) in another file silenced the texture warning")

    # --- digests: how the packaged payload is tracked
    def test_content_file_changes_the_package_digest(self):
        mod = self._mod({"Plugin.cs": "class P {}"})
        (mod / "content").mkdir()
        asset = mod / "content" / "README.md"          # same name as a root document
        asset.write_text("v1", encoding="utf-8")
        before, source_before = core.package_digest(mod), core.source_digest(mod)
        asset.write_text("v2", encoding="utf-8")
        self.assertNotEqual(before, core.package_digest(mod),
                            "content/README.md is packaged but its change did not alter the digest")
        self.assertEqual(source_before, core.source_digest(mod),
                         "a content asset must not change the compile digest")

    def test_root_documents_do_not_change_the_compile_digest(self):
        mod = self._mod({"Plugin.cs": "class P {}"})
        (mod / "README.md").write_text("one", encoding="utf-8")
        source, package = core.source_digest(mod), core.package_digest(mod)
        (mod / "README.md").write_text("two", encoding="utf-8")
        self.assertEqual(source, core.source_digest(mod),
                         "documentation must not invalidate a compiled build")
        self.assertNotEqual(package, core.package_digest(mod),
                            "the README is packaged, so its change belongs to packaging provenance")

    # --- release preflight
    def test_package_refuses_on_blocking_audit_findings(self):
        import shutil
        shutil.copytree(REAL_ROOT / "templates", self.root / "templates")
        shutil.copyfile(REAL_ROOT / "NuGet.Config", self.root / "NuGet.Config")
        with patch.object(core, "ROOT", self.root):
            core.new_mod("Preflight", "Team")
            folder = core.project("Preflight")
            dll = folder / "build/bin/Preflight.dll"
            dll.parent.mkdir(parents=True, exist_ok=True)
            dll.write_bytes(b"MZ" + b"fixture")
            (folder / "src" / "Extra.cs").write_text(
                "global using R2API.Skins;" + chr(10) + "class X {}", encoding="utf-8")
            core.write_json(folder / "build/receipt.json", {
                "assembly_sha256": core.sha256(dll),
                "source_sha256": core.source_digest(folder),
                "package_sha256": core.package_digest(folder),
            })
            with self.assertRaises(ValueError) as raised:
                core.package_mod("Preflight")
            self.assertIn("audit failed", str(raised.exception))

    def test_version_backup_csproj_does_not_fail_the_audit(self):
        """`forge bump` keeps the previous csproj in build/version-backups; that copy is not the project."""
        mod = self._mod({"Plugin.cs": 'class P { const string PluginVersion = "1.0.0"; }'})
        (mod / "src" / "AuditMod.csproj").write_text(
            "<Project><PropertyGroup><Version>1.0.0</Version></PropertyGroup></Project>", encoding="utf-8")
        backup = mod / "build" / "version-backups"
        backup.mkdir(parents=True)
        (backup / "AuditMod.csproj").write_text(
            "<Project><PropertyGroup><Version>0.9.9</Version></PropertyGroup></Project>", encoding="utf-8")
        result = core.audit_project(mod)
        self.assertTrue(result["valid"], result["errors"])


if __name__ == "__main__":
    unittest.main()
