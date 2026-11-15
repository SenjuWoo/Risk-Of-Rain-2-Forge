"""`forge updates` covers the pins `forge new` writes into every mod, not only the toolchain's.

The scaffold's Thunderstore dependencies and the stats template's R2API NuGet reference were invisible to the update
report: RoR2BepInExPack 1.50.0 was live against the template's 1.49.0 and nothing said so.
"""
import json
import pathlib
import tempfile
from unittest import TestCase, main
from unittest.mock import patch

from ror2forge import core, updates

TS = "https://thunderstore.io/api/experimental/package/"


def thunderstore(latest, deprecated=False, missing_pins=()):
    """Fixture feed: package endpoints return `latest`; a version endpoint fails for a missing pin."""
    def fetch(url):
        rest = url[len(TS):].strip("/").split("/")
        if len(rest) == 3:
            if tuple(rest) in missing_pins:
                raise ValueError("HTTP Error 404: Not Found")
            return {"version_number": rest[2]}
        return {"latest": {"version_number": latest}, "is_deprecated": deprecated}
    return fetch


class ScaffoldPinTests(TestCase):
    def test_new_mod_writes_the_tracked_pins(self):
        with tempfile.TemporaryDirectory(dir=core.ROOT / "artifacts") as scratch:
            root = pathlib.Path(scratch)
            (root / "templates").mkdir()
            for name in ("plugin.cs", "stats.cs"):
                (root / "templates" / name).write_text((core.PACKAGE_ROOT / "templates" / name).read_text(encoding="utf-8"),
                                                       encoding="utf-8")
            with patch.object(core, "ROOT", root):
                plain = core.new_mod("Plain", "Team")
                stats = core.new_mod("Stats", "Team", "stats")
            plain_deps = core.read_json(pathlib.Path(plain["project"]) / "manifest.json")["dependencies"]
            stats_deps = core.read_json(pathlib.Path(stats["project"]) / "manifest.json")["dependencies"]
            stats_csproj = (pathlib.Path(stats["project"]) / "src/Stats.csproj").read_text(encoding="utf-8")
        self.assertEqual(plain_deps, list(core.SCAFFOLD_DEPENDENCIES))
        self.assertEqual(stats_deps, list(core.SCAFFOLD_DEPENDENCIES) + list(core.STATS_DEPENDENCIES))
        for package, version in core.STATS_REFERENCES.items():
            self.assertIn(f'Include="{package}" Version="[{version}]"', stats_csproj)


class ThunderstoreCheckTests(TestCase):
    JOB = ("RiskofThunder-RoR2BepInExPack", "1.49.0", TS + "RiskofThunder/RoR2BepInExPack/", None)

    def check(self, fetch):
        with patch.object(updates, "_json", side_effect=fetch):
            return updates._check(self.JOB)

    def test_newer_release_is_an_update_and_says_the_pin_is_a_minimum(self):
        result = self.check(thunderstore("1.50.0"))
        self.assertEqual((result["status"], result["latest"]), ("update_available", "1.50.0"))
        self.assertIn("minimum", result["policy"])
        self.assertEqual(result["kind"], "thunderstore")

    def test_matching_release_is_current(self):
        self.assertEqual(self.check(thunderstore("1.49.0"))["status"], "current")

    def test_a_pin_the_site_no_longer_serves_is_unknown(self):
        result = self.check(thunderstore("1.50.0", missing_pins={("RiskofThunder", "RoR2BepInExPack", "1.49.0")}))
        self.assertEqual(result["status"], "unknown")
        self.assertIn("404", result["error"])

    def test_latest_older_than_the_pin_is_unknown(self):
        self.assertEqual(self.check(thunderstore("1.48.0"))["status"], "unknown")

    def test_malformed_latest_is_unknown(self):
        for bad in (None, "", "garbage", 5):
            with self.subTest(latest=bad):
                self.assertEqual(self.check(thunderstore(bad))["status"], "unknown")

    def test_deprecated_package_is_flagged(self):
        result = self.check(thunderstore("1.49.0", deprecated=True))
        self.assertTrue(result["deprecated"])
        self.assertIn("deprecated", result["policy"])


class ReportTests(TestCase):
    @staticmethod
    def feeds(url):
        if url.startswith(TS):
            return thunderstore("99.0.0")(url)
        if url == updates.PYPI:
            return {"info": {"version": updates.toolchain.MCP_VERSION},
                    "releases": {updates.toolchain.MCP_VERSION: [{"yanked": False}]}}
        package = url.split("/")[-2]
        pins = {name.lower(): version for name, version in
                {**updates.toolchain.DOTNET_TOOLS, **updates.core.PINS, **updates.core.STATS_REFERENCES}.items()}
        return {"versions": [pins[package]]}

    def test_report_lists_every_template_pin(self):
        with patch.object(updates, "_bepinex_base", return_value="https://nuget.bepinex.dev/v3/package/"), \
                patch.object(updates, "_json", side_effect=self.feeds):
            result = updates.check_updates()
        entries = {entry["package"]: entry for entry in result["entries"]}
        for dependency in (*core.SCAFFOLD_DEPENDENCIES, *core.STATS_DEPENDENCIES):
            name, version = dependency.rsplit("-", 1)
            self.assertEqual(entries[name]["pinned"], version)
            self.assertEqual(entries[name]["status"], "update_available")
        for package, version in core.STATS_REFERENCES.items():
            self.assertEqual((entries[package]["pinned"], entries[package]["status"]), (version, "current"))
        self.assertTrue(result["complete"])
        self.assertEqual(result["updates_available"], len(core.SCAFFOLD_DEPENDENCIES) + len(core.STATS_DEPENDENCIES))
        self.assertEqual(json.loads(json.dumps(result)), result)


if __name__ == "__main__":
    main()
