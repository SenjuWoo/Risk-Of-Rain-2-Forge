"""The compiled assembly is the authority for R2API dependencies; the source scanner stays advisory."""
import json
import pathlib
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from unittest import mock

from ror2forge import core

ROOT = core.ROOT
MOD = {
    "name": "AsmTest",
    "version_number": "1.0.0",
    "website_url": "",
    "description": "d",
    "dependencies": [],
}


class AssemblyAuditTests(unittest.TestCase):
    def setUp(self):
        area = ROOT / "artifacts/test-temp"
        area.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=area)
        self.root = pathlib.Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def _project(self, dependencies):
        (self.root / "manifest.json").write_text(
            json.dumps({**MOD, "dependencies": dependencies}), encoding="utf-8")
        (self.root / "src").mkdir(exist_ok=True)
        (self.root / "src/Plugin.cs").write_text(textwrap.dedent("""
            using BepInEx;
            namespace AsmTest { [BepInPlugin("x.y.z", "AsmTest", "1.0.0")] public class Plugin : BaseUnityPlugin { } }
        """), encoding="utf-8")
        built = self.root / "build/bin"
        built.mkdir(parents=True, exist_ok=True)
        (built / "AsmTest.dll").write_bytes(b"MZ")      # the reader is mocked; the file only has to exist

    def _audit(self, references, dependencies):
        self._project(dependencies)
        payload = {"status": "ok", "assembly": "AsmTest", "version": "1.0.0.0",
                   "references": [{"name": name, "version": "1.0.0.0"} for name in references]}
        with mock.patch.object(core, "assembly_refs", return_value=payload):
            return core.audit_project(self.root)

    def test_missing_r2api_package_is_an_error_even_when_the_source_is_clean(self):
        """An extension method reached through `using static` leaves no namespace for the scanner to see."""
        result = self._audit(["R2API.Skins", "UnityEngine"], [])
        self.assertFalse(result["valid"], result)
        self.assertTrue(any("R2API.Skins" in error for error in result["errors"]), result["errors"])

    def test_declared_package_satisfies_the_compiled_reference(self):
        result = self._audit(["R2API.Skins"], ["RiskofThunder-R2API_Skins-1.2.3"])
        self.assertTrue(result["valid"], result["errors"])

    def test_core_reference_maps_to_the_core_package(self):
        result = self._audit(["R2API"], [])
        self.assertTrue(any("R2API_Core" in error for error in result["errors"]), result["errors"])

    def test_non_r2api_references_are_ignored(self):
        result = self._audit(["UnityEngine", "BepInEx", "RoR2"], [])
        self.assertTrue(result["valid"], result["errors"])

    def test_a_missing_assembly_is_reported_not_fatal(self):
        self._project([])
        shutil.rmtree(self.root / "build")          # nothing compiled yet
        result = core.audit_project(self.root)
        self.assertEqual(result["assembly"]["status"], "skipped", result["assembly"])

    def test_unavailable_reader_does_not_block_the_audit(self):
        self._project([])
        with mock.patch.object(core, "assembly_refs", side_effect=ValueError("no dotnet")):
            result = core.audit_project(self.root)
        self.assertEqual(result["assembly"]["status"], "unavailable", result["assembly"])
        self.assertTrue(result["valid"], result["errors"])


@unittest.skipUnless(shutil.which("dotnet"), "no .NET SDK on this machine")
class AssemblyReaderTests(unittest.TestCase):
    def test_reads_references_without_loading_the_assembly(self):
        target = core.ASMREFS_DLL if core.ASMREFS_DLL.is_file() else None
        if target is None:
            self.skipTest("the assembly reader has not been built yet")
        payload = core.assembly_refs(target)
        self.assertEqual(payload["status"], "ok")
        names = {ref["name"] for ref in payload["references"]}
        self.assertIn("System.Reflection.Metadata", names)
        self.assertEqual(payload["assembly"], "asmrefs")

    def test_rejects_a_file_that_is_not_a_managed_assembly(self):
        with tempfile.TemporaryDirectory() as scratch:
            junk = pathlib.Path(scratch) / "junk.dll"
            junk.write_bytes(b"not a pe file")
            with self.assertRaises(ValueError):
                core.assembly_refs(junk)


if __name__ == "__main__":
    unittest.main()
