"""Build readiness is independent of a local game; inspection is not."""
import subprocess
import unittest
from unittest.mock import patch

from ror2forge import core


class DoctorTests(unittest.TestCase):
    def report(self, sdks, executable="dotnet", selected="8.0.426", selection_error=None):
        results = [subprocess.CompletedProcess([], 0, sdks, ""), subprocess.CompletedProcess([], 1 if selection_error else 0, selected, selection_error or "")]
        with patch.object(core, "discover", return_value={"game_dir": None, "profiles": []}), patch.object(core.shutil, "which", return_value=executable), patch.object(core.subprocess, "run", side_effect=results):
            return core.doctor()

    def test_game_free_build_is_ready_with_supported_sdk(self):
        report = self.report("8.0.426 [SDK]\n10.0.403 [SDK]\n")
        self.assertTrue(report["ready_for_build"])
        self.assertFalse(report["ready_for_inspection"])
        self.assertIsNone(report["game_dir"])

    def test_old_sdk_does_not_support_template_language(self):
        self.assertFalse(self.report("7.0.100 [SDK]\n", selected="7.0.100")["ready_for_build"])

    def test_runtime_without_sdk_is_not_ready(self):
        self.assertFalse(self.report("", selected="", selection_error="No SDK found")["ready_for_build"])
        self.assertFalse(self.report("", executable=None)["ready_for_build"])

    def test_unresolvable_global_sdk_is_not_ready_despite_newer_inventory(self):
        report = self.report("8.0.426 [SDK]\n10.0.403 [SDK]\n", selected="", selection_error="global.json selects unavailable SDK")
        self.assertFalse(report["ready_for_build"])
        self.assertIsNone(report["selected_sdk"])
        self.assertIn("global.json", report["sdk_error"])

    def test_pinned_older_sdk_is_not_overridden_by_inventory(self):
        self.assertFalse(self.report("10.0.403 [SDK]\n", selected="7.0.100")["ready_for_build"])


if __name__ == "__main__":
    unittest.main()
