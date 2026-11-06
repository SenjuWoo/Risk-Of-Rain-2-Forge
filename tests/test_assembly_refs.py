"""The compiled assembly is the authority for R2API dependencies; the source scanner stays advisory.

Covers the three defects an independent review reproduced: a crash when no .NET SDK exists, selecting whichever
DLL happens to be newest, and a stale cached reader surviving a source change.
"""
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
MOD = {"name": "AsmTest", "version_number": "1.0.0", "website_url": "", "description": "d", "dependencies": []}


class Fixture(unittest.TestCase):
    def setUp(self):
        area = ROOT / "artifacts/test-temp"
        area.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=area)
        self.root = pathlib.Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def project(self, dependencies=(), dlls=("AsmTest.dll",), receipt=None):
        (self.root / "manifest.json").write_text(json.dumps({**MOD, "dependencies": list(dependencies)}),
                                                 encoding="utf-8")
        (self.root / "src").mkdir(exist_ok=True)
        (self.root / "src/Plugin.cs").write_text(textwrap.dedent("""
            using BepInEx;
            namespace AsmTest { [BepInPlugin("x.y.z", "AsmTest", "1.0.0")] public class Plugin : BaseUnityPlugin { }
        """), encoding="utf-8")
        built = self.root / "build/bin"
        built.mkdir(parents=True, exist_ok=True)
        for name in dlls:
            # Stand-in for a managed build: the reader is mocked here, but the CLI signature must be present.
            (built / name).write_bytes(b"MZBSJB stub")
        if receipt is not None:
            (self.root / "build").mkdir(exist_ok=True)
            (self.root / "build/receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
        return self.root

    @staticmethod
    def refs(*names):
        return {"status": "ok", "assembly": "AsmTest", "version": "1.0.0.0",
                "references": [{"name": n, "version": "1.0.0.0"} for n in names]}


class SelectionTests(Fixture):
    def test_the_build_receipt_names_the_assembly_that_is_inspected(self):
        self.project(dlls=("AsmTest.dll", "Unrelated.dll"), receipt={"assembly": "build/bin/AsmTest.dll"})
        seen = []

        def capture(path):
            seen.append(pathlib.Path(path).name)
            return self.refs("R2API.Skins")

        with mock.patch.object(core, "assembly_refs", side_effect=capture):
            result = core.audit_project(self.root)
        self.assertEqual(seen, ["AsmTest.dll"], "the receipt's assembly must win over timestamps")
        self.assertTrue(any("R2API.Skins" in e for e in result["errors"]))

    def test_a_newer_unrelated_dll_is_never_selected(self):
        root = self.project(dlls=("AsmTest.dll", "Unrelated.dll"))
        newer = root / "build/bin/Unrelated.dll"
        newer.write_bytes(b"MZBSJB newer")
        import os
        os.utime(newer, (2_000_000_000, 2_000_000_000))
        seen = []

        def capture(path):
            seen.append(pathlib.Path(path).name)
            return self.refs()

        with mock.patch.object(core, "assembly_refs", side_effect=capture):
            core.audit_project(root)
        self.assertEqual(seen, ["AsmTest.dll"])

    def test_mismatched_names_are_refused_rather_than_guessed(self):
        self.project(dlls=("Alpha.dll", "Beta.dll"))
        with mock.patch.object(core, "assembly_refs") as reader:
            result = core.audit_project(self.root)
        reader.assert_not_called()
        self.assertEqual(result["assembly"]["status"], "skipped")
        self.assertIn("several assemblies", result["assembly"]["reason"])

    def test_a_receipt_pointing_outside_the_project_is_refused(self):
        self.project()
        (self.root / "build/receipt.json").write_text(json.dumps({"assembly": "../../evil.dll"}), encoding="utf-8")
        with mock.patch.object(core, "assembly_refs") as reader:
            result = core.audit_project(self.root)
        reader.assert_not_called()
        self.assertEqual(result["assembly"]["status"], "skipped")


class ToolchainTests(Fixture):
    def test_missing_dotnet_is_advisory_and_keeps_other_errors(self):
        self.project()
        (self.root / "manifest.json").write_text(json.dumps({**MOD, "version_number": "1.0.0"}), encoding="utf-8")
        with mock.patch.object(core, "ASMREFS_DLL", self.root / "absent.dll"), \
                mock.patch.object(core, "ASMREFS_STAMP", self.root / "absent.stamp"), \
                mock.patch.object(core.shutil, "which", return_value=None):
            result = core.audit_project(self.root)
        self.assertEqual(result["assembly"]["status"], "unavailable")
        self.assertIn("no .NET SDK", result["assembly"]["reason"])

    def test_a_process_launch_failure_is_advisory(self):
        self.project(receipt={"assembly": "build/bin/AsmTest.dll"})
        boom = FileNotFoundError(2, "No such file or directory", "dotnet")
        with mock.patch.object(core, "ASMREFS_DLL", self.root / "absent.dll"), \
                mock.patch.object(core, "ASMREFS_STAMP", self.root / "absent.stamp"), \
                mock.patch.object(core.shutil, "which", return_value="/usr/bin/dotnet"), \
                mock.patch.object(core.subprocess, "run", side_effect=boom):
            result = core.audit_project(self.root)
        self.assertEqual(result["assembly"]["status"], "unavailable")
        self.assertIn("cannot start dotnet", result["assembly"]["reason"])

    def test_an_invalid_assembly_is_a_real_error_not_an_advisory(self):
        self.project()
        with mock.patch.object(core, "assembly_refs", side_effect=ValueError("not a managed assembly")):
            result = core.audit_project(self.root)
        self.assertEqual(result["assembly"]["status"], "invalid")
        self.assertFalse(result["valid"])
        self.assertIn("could not be inspected", " ".join(result["errors"]))


class ReaderFreshnessTests(unittest.TestCase):
    def test_a_changed_reader_source_forces_a_rebuild(self):
        with tempfile.TemporaryDirectory() as scratch:
            scratch = pathlib.Path(scratch)
            dll, stamp = scratch / "asmrefs.dll", scratch / ".source-sha256"
            dll.write_bytes(b"old")
            stamp.write_text("stale-hash")
            calls = []

            def fake_run(argv, **kwargs):
                calls.append(argv)
                if "build" in argv:
                    dll.write_bytes(b"new")
                return subprocess.CompletedProcess(argv, 0, "", "")

            with mock.patch.object(core, "ASMREFS_DLL", dll), mock.patch.object(core, "ASMREFS_STAMP", stamp), \
                    mock.patch.object(core, "_reader_sources_hash", return_value="fresh-hash"), \
                    mock.patch.object(core.shutil, "which", return_value="/usr/bin/dotnet"), \
                    mock.patch.object(core.subprocess, "run", side_effect=fake_run):
                core._ensure_reader()
            self.assertTrue(calls and "build" in calls[0], calls)
            self.assertEqual(stamp.read_text(), "fresh-hash")

    def test_an_up_to_date_reader_is_not_rebuilt(self):
        with tempfile.TemporaryDirectory() as scratch:
            scratch = pathlib.Path(scratch)
            dll, stamp = scratch / "asmrefs.dll", scratch / ".source-sha256"
            dll.write_bytes(b"current")
            stamp.write_text("fresh-hash")
            with mock.patch.object(core, "ASMREFS_DLL", dll), mock.patch.object(core, "ASMREFS_STAMP", stamp), \
                    mock.patch.object(core, "_reader_sources_hash", return_value="fresh-hash"), \
                    mock.patch.object(core.subprocess, "run") as runner:
                core._ensure_reader()
            runner.assert_not_called()


@unittest.skipUnless(shutil.which("dotnet"), "no .NET SDK on this machine")
class RealReaderTests(unittest.TestCase):
    def test_reads_references_without_loading_the_assembly(self):
        if not core.ASMREFS_DLL.is_file():
            self.skipTest("the assembly reader has not been built yet")
        payload = core.assembly_refs(core.ASMREFS_DLL)
        self.assertEqual(payload["status"], "ok")
        self.assertIn("System.Reflection.Metadata", {r["name"] for r in payload["references"]})

    def test_rejects_a_file_that_is_not_a_managed_assembly(self):
        with tempfile.TemporaryDirectory() as scratch:
            junk = pathlib.Path(scratch) / "junk.dll"
            junk.write_bytes(b"not a pe file")
            with self.assertRaises(ValueError):
                core.assembly_refs(junk)


if __name__ == "__main__":
    unittest.main()
