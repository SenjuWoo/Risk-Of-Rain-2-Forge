"""Bounded API discovery tests; real ILSpy/type inventory is exercised by CI smoke.

Fixtures cover deterministic matching, generated helpers, and trust boundaries.
"""
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import subprocess

from ror2forge import core
from ror2forge.cli import main


class SymbolTests(unittest.TestCase):
    def setUp(self):
        area = core.ROOT / "artifacts/test-temp"
        area.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=area)
        self.assembly = Path(self.temp.name) / "Example.dll"
        self.assembly.write_bytes(b"assembly fixture")

    def tearDown(self):
        self.temp.cleanup()

    def test_exact_result_first_and_output_bounded(self):
        listing = "Class RoR2.Body+Nested\nClass RoR2.Body\nClass RoR2.Body+<>c\nStruct RoR2.BodyData\nInterface RoR2.IBody\nEnum RoR2.BodyIndex\nDelegate RoR2.BodyCallback\n"
        with patch.object(core, "run_process", return_value=subprocess.CompletedProcess([], 0, listing, "")) as run:
            result = core.symbols("ror2.body", str(self.assembly), 2)
        self.assertEqual(result["total"], 5)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["symbols"][0], {"kind": "class", "name": "RoR2.Body"})
        self.assertEqual(result["assembly_sha256"], core.sha256(self.assembly))
        self.assertIn("cisde", run.call_args.args[0])

    def test_empty_search_and_bad_limit_fail_before_tool(self):
        for query, limit in (("", 1), (" ", 1), ("a\n", 1), ("a" * 257, 1), ("a", 0), ("a", 201)):
            with self.subTest(query=query, limit=limit), patch.object(core, "run_process") as run:
                with self.assertRaises(ValueError):
                    core.symbols(query, str(self.assembly), limit)
                run.assert_not_called()

    def test_missing_or_non_dll_assembly_is_rejected(self):
        for selected in (self.assembly.with_name("missing.dll"), self.assembly.with_suffix(".txt")):
            selected.with_suffix(".txt").write_text("not a DLL")
            with self.assertRaises(ValueError):
                core.symbols("anything", str(selected))

    def test_default_discovery_and_empty_result(self):
        with patch.object(core, "discover", return_value={"assembly": str(self.assembly)}), patch.object(core, "run_process", return_value=subprocess.CompletedProcess([], 0, "Class Other.Type\n", "")):
            result = core.symbols("notfound")
        self.assertEqual(result["symbols"], [])
        self.assertFalse(result["truncated"])

    def test_cli_structured_symbol_output(self):
        output = io.StringIO()
        with patch.object(core, "symbols", return_value={"symbols": []}) as lookup, redirect_stdout(output):
            self.assertEqual(main(["symbols", "Body", "--assembly", str(self.assembly), "--limit", "5"]), 0)
        lookup.assert_called_once_with("Body", str(self.assembly), 5)
        self.assertEqual(json.loads(output.getvalue()), {"symbols": []})


if __name__ == "__main__":
    unittest.main()
