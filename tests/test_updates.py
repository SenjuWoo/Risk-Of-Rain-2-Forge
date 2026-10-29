"""Official feed fixture checks; no network access or installed tool changes."""
import io
import json
from contextlib import redirect_stdout
from unittest import TestCase, main
from unittest.mock import patch

from ror2forge import updates
from ror2forge.cli import main as cli_main


class UpdateTests(TestCase):
    def test_cli_unknown_results_have_nonzero_exit_and_json_report(self):
        output = io.StringIO()
        with patch.object(updates, "check_updates", return_value={"complete": False, "entries": [{"status": "unknown"}]}), redirect_stdout(output):
            self.assertEqual(cli_main(["updates"]), 1)
        self.assertFalse(json.loads(output.getvalue())["complete"])

    def test_available_update_is_not_a_failed_lookup(self):
        output = io.StringIO()
        with patch.object(updates, "check_updates", return_value={"complete": True, "updates_available": 1}), redirect_stdout(output):
            self.assertEqual(cli_main(["updates"]), 0)
        self.assertEqual(json.loads(output.getvalue())["updates_available"], 1)

    def test_unsorted_nuget_versions_ignore_preview_and_order_numerically(self):
        result = updates._select("ilspycmd", "11.2.0.10050", ["11.10.0.1", "12.0.0-preview.1", "11.2.0.10050", "11.3.0.1"])
        self.assertEqual(result["latest"], "11.10.0.1")
        self.assertEqual(result["status"], "update_available")

    def test_game_reference_revisions_are_not_discarded(self):
        result = updates._select("RiskOfRain2.GameLibs", "1.5.0-r.1", ["1.5.0-r.10", "1.5.0-r.1", "2.0.0-preview.1", "1.5.0-r.2"])
        self.assertEqual(result["latest"], "1.5.0-r.10")
        self.assertIn("target game", result["policy"])

    def test_unrelated_loader_and_unity_generations_are_excluded(self):
        loader = updates._select("BepInEx.Core", "5.4.21", ["6.0.0", "5.4.21", "6.0.1-be.1"])
        unity = updates._select("UnityEngine.Modules", "2021.3.45", ["6000.6.4", "2021.3.45", "2022.3.8", "2021.3.46"])
        self.assertEqual(loader["status"], "current")
        self.assertEqual(unity["latest"], "2021.3.46")

    def test_absent_pin_and_malformed_versions_are_not_current(self):
        for versions in ([], ["1.0.0"], [None], ["11.2.0.10050", "garbage"]):
            with self.subTest(versions=versions), self.assertRaises(ValueError):
                updates._select("ilspycmd", "11.2.0.10050", versions)

    def test_pypi_excludes_yanked_and_prerelease_versions(self):
        metadata = {"info": {"version": "2.3.0"}, "releases": {"2.3.0": [{"yanked": False}], "2.4.0": [{"yanked": True}], "3.0.0rc1": [{"yanked": False}]}}
        with patch.object(updates, "_json", return_value=metadata):
            result = updates._check(("mcp", "2.3.0", updates.PYPI, None))
        self.assertEqual(result["status"], "current")
        self.assertEqual(result["latest"], "2.3.0")

    def test_partial_failure_is_reported_without_losing_other_results(self):
        def metadata(url):
            if "tcli" in url:
                raise TimeoutError("feed timed out")
            if url == updates.PYPI:
                return {"info": {"version": updates.toolchain.MCP_VERSION}, "releases": {updates.toolchain.MCP_VERSION: [{"yanked": False}]}}
            package = url.split("/")[-2]
            pins = {name.lower(): version for name, version in {**updates.toolchain.DOTNET_TOOLS, **updates.core.PINS}.items()}
            return {"versions": [pins[package]]}
        with patch.object(updates, "_bepinex_base", return_value="https://nuget.bepinex.dev/v3/package/"), patch.object(updates, "_json", side_effect=metadata):
            result = updates.check_updates()
        self.assertFalse(result["complete"])
        failed = next(entry for entry in result["entries"] if entry["package"] == "tcli")
        self.assertEqual(failed["status"], "unknown")
        self.assertIn("timed out", failed["error"])
        self.assertEqual(sum(entry["status"] == "current" for entry in result["entries"]), len(result["entries"]) - 1)

    def test_service_index_failure_marks_only_reference_packages_unknown(self):
        def metadata(url):
            if url == updates.PYPI:
                return {"info": {"version": updates.toolchain.MCP_VERSION}, "releases": {updates.toolchain.MCP_VERSION: [{"yanked": False}]}}
            package = url.split("/")[-2]
            return {"versions": [updates.toolchain.DOTNET_TOOLS[package]]}
        with patch.object(updates, "_bepinex_base", side_effect=ValueError("no service endpoint")), patch.object(updates, "_json", side_effect=metadata):
            result = updates.check_updates()
        self.assertFalse(result["complete"])
        for entry in result["entries"]:
            self.assertEqual(entry["status"], "unknown" if entry["package"] in updates.core.PINS else "current")

    def test_service_endpoint_is_discovered_and_external_hosts_rejected(self):
        for endpoint, accepted in (("https://nuget.bepinex.dev/v3/package", True), ("https://example.org/", False), ("http://nuget.bepinex.dev/v3/package", False)):
            with self.subTest(endpoint=endpoint), patch.object(updates, "_json", return_value={"resources": [{"@type": "PackageBaseAddress/3.0.0", "@id": endpoint}]}):
                if accepted:
                    self.assertEqual(updates._bepinex_base(), endpoint + "/")
                else:
                    with self.assertRaises(ValueError):
                        updates._bepinex_base()

    def test_download_size_and_json_shape_are_bounded(self):
        for data in (b"x" * (updates.MAX_RESPONSE + 1), b"[]", b"not JSON"):
            with self.subTest(length=len(data)), patch.object(updates.urllib.request, "urlopen", return_value=io.BytesIO(data)):
                with self.assertRaises(ValueError):
                    updates._json(updates.PYPI)

    def test_invalid_feed_metadata_is_unknown(self):
        with patch.object(updates, "_json", return_value={"versions": "not a list"}):
            result = updates._check(("tcli", "0.2.4", "https://api.nuget.org/v3-flatcontainer/tcli/index.json", None))
        self.assertEqual(result["status"], "unknown")
        self.assertIsNone(result["latest"])

    def test_unsupported_pypi_release_does_not_claim_old_pin_current(self):
        metadata = {"info": {"version": "2.3.0.post1"}, "releases": {"2.3.0": [{"yanked": False}], "2.3.0.post1": [{"yanked": False}]}}
        with patch.object(updates, "_json", return_value=metadata):
            result = updates._check(("mcp", "2.3.0", updates.PYPI, None))
        self.assertEqual(result["status"], "unknown")


if __name__ == "__main__":
    main()
