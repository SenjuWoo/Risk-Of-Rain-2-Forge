"""Regressions from the 1.16.0 whole-project audit.

Each case reproduced a defect against 1.15.7: false blocking errors for the R2API Rulebook package and for unrelated
version constants, version drift the audit could not see, a string form that hid the code after it, raw Python
exceptions on malformed project files, and a release gate that never looked at the CodeQL checks.
"""
import json
import subprocess
from unittest.mock import patch

from test_final_audit import Fixture
from ror2forge import core

PLUGIN = '[BepInPlugin("team.mod", "AuditMod", PluginVersion)] class P { public const string PluginVersion = "1.0.0"; %s }'


class PackageNameTests(Fixture):
    def test_rules_guid_is_satisfied_by_the_rulebook_package(self):
        mod = self.mod({"P.cs": '[BepInDependency("com.bepis.r2api.rules")] ' + PLUGIN % ""},
                       deps=["RiskofThunder-R2API_Rulebook-1.0.2"])
        result = core.audit_project(mod)
        self.assertTrue(result["valid"], result["errors"])

    def test_missing_rules_dependency_names_the_real_package(self):
        mod = self.mod({"P.cs": '[BepInDependency("com.bepis.r2api.rules")] ' + PLUGIN % ""})
        errors = core.audit_project(mod)["errors"]
        self.assertTrue(any("R2API_Rulebook" in e for e in errors), errors)
        self.assertFalse(any("R2API_rules" in e for e in errors), errors)

    def test_utils_message_names_core_not_a_package_that_does_not_exist(self):
        mod = self.mod({"P.cs": "using R2API.Utils;\n" + PLUGIN % ""})
        errors = core.audit_project(mod)["errors"]
        self.assertTrue(any("R2API_Core" in e for e in errors), errors)
        self.assertFalse(any("R2API_Utils" in e for e in errors), errors)

    def _compiled(self, references, deps):
        mod = self.mod({"P.cs": PLUGIN % ""}, deps=deps)
        built = mod / "build/bin"
        built.mkdir(parents=True, exist_ok=True)
        (built / "mod.dll").write_bytes(b"MZBSJB stub")
        payload = {"status": "ok", "assembly": "mod", "version": "1.0.0.0",
                   "references": [{"name": name, "version": "1.0.0.0"} for name in references]}
        with patch.object(core, "assembly_refs", return_value=payload):
            return core.audit_project(mod)

    def test_compiled_rules_reference_is_satisfied_by_rulebook(self):
        result = self._compiled(["R2API.Rules"], ["RiskofThunder-R2API_Rulebook-1.0.2"])
        self.assertTrue(result["valid"], result["errors"])

    def test_compiled_rules_reference_without_rulebook_names_it(self):
        errors = self._compiled(["R2API.Rules"], [])["errors"]
        self.assertTrue(any("R2API_Rulebook" in e for e in errors), errors)

    def test_interop_and_runtime_assemblies_belong_to_their_module(self):
        result = self._compiled(["R2API.Skills.Interop", "R2API.Animations.Runtime"],
                                ["RiskofThunder-R2API_Skills-1.0.6", "RiskofThunder-R2API_Animations-1.2.5"])
        self.assertTrue(result["valid"], result["errors"])

    def test_legacy_r2api_reference_names_the_legacy_package(self):
        errors = self._compiled(["R2API"], ["RiskofThunder-R2API_Core-5.3.0"])["errors"]
        self.assertTrue(any("tristanmcpherson-R2API" in e for e in errors), errors)
        self.assertTrue(self._compiled(["R2API"], ["tristanmcpherson-R2API-5.0.5"])["valid"])

    def test_an_unrelated_assembly_that_merely_starts_with_r2api_is_ignored(self):
        self.assertTrue(self._compiled(["R2APIHelperByAnotherTeam"], [])["valid"])

    def test_every_package_override_names_a_known_module(self):
        for module in core.R2API_PACKAGE_NAMES:
            self.assertIn(module, core.R2API_MODULES)


class VersionConstantTests(Fixture):
    def test_unrelated_version_constants_do_not_block(self):
        mod = self.mod({"P.cs": PLUGIN % 'const string ConfigVersion = "2.0.0"; const string MinGameVersion = "1.3.9";'})
        result = core.audit_project(mod)
        self.assertTrue(result["valid"], result["errors"])

    def test_plugin_constant_drift_is_still_an_error(self):
        mod = self.mod({"P.cs": (PLUGIN % "").replace('"1.0.0"', '"1.0.1"')})
        self.assertTrue(any("1.0.1" in e for e in core.audit_project(mod)["errors"]))

    def test_upper_case_constant_named_by_the_attribute_is_checked(self):
        mod = self.mod({"P.cs": '[BepInPlugin("a.b", "AuditMod", PLUGIN_VERSION)] class P { const string PLUGIN_VERSION = "0.9.0"; }'})
        self.assertTrue(any("0.9.0" in e for e in core.audit_project(mod)["errors"]))

    def test_qualified_constant_in_another_file_is_checked(self):
        mod = self.mod({"P.cs": '[BepInPlugin(Info.Guid, Info.Name, Info.Ver)] class P { }',
                        "Info.cs": 'static class Info { public const string Guid = "a.b", Name = "n"; public const string Ver = "3.0.0"; }'})
        self.assertTrue(any("3.0.0" in e for e in core.audit_project(mod)["errors"]))

    def test_literal_attribute_version_is_checked(self):
        mod = self.mod({"P.cs": '[BepInPlugin("a.b", "Audit, Mod (x)", "0.5.0")] class P { }'})
        self.assertTrue(any("0.5.0" in e for e in core.audit_project(mod)["errors"]))

    def test_matching_literal_attribute_passes(self):
        mod = self.mod({"P.cs": '[BepInPlugin("a.b", "AuditMod", "1.0.0")] class P { }'})
        self.assertTrue(core.audit_project(mod)["valid"])

    def test_a_second_dev_plugin_in_the_tree_warns_when_the_main_one_matches(self):
        # Found on a real survivor: tools/dumper carries its own [BepInPlugin(..., "1.0.0")] and never ships.
        mod = self.mod({"P.cs": PLUGIN % "",
                        "Dumper.cs": '[BepInPlugin("woo.dumper", "Dumper", "0.1.0")] class D { }'})
        result = core.audit_project(mod)
        self.assertTrue(result["valid"], result["errors"])
        self.assertTrue(any("0.1.0" in w for w in result["warnings"]), result["warnings"])

    def test_two_plugins_and_neither_matches_is_an_error(self):
        mod = self.mod({"P.cs": (PLUGIN % "").replace('"1.0.0"', '"0.9.0"'),
                        "Dumper.cs": '[BepInPlugin("woo.dumper", "Dumper", "0.1.0")] class D { }'})
        self.assertFalse(core.audit_project(mod)["valid"])

    def test_without_a_plugin_attribute_the_named_constant_is_still_compared(self):
        mod = self.mod({"P.cs": 'class P { const string PluginVersion = "4.0.0"; }'})
        self.assertTrue(any("4.0.0" in e for e in core.audit_project(mod)["errors"]))


class LexerTests(Fixture):
    def test_verbatim_interpolated_string_ending_in_a_backslash_does_not_hide_code(self):
        stripped = core._strip_csharp('a = $@"{r}\\"; b = SkillsAPI.X; // c')
        self.assertIn("SkillsAPI.X", stripped)
        self.assertNotIn("// c", stripped)

    def test_either_prefix_order_and_doubled_quotes(self):
        for prefix in ('$@', '@$'):
            stripped = core._strip_csharp(f'a = {prefix}"x ""SkillsAPI"" y"; b = 1;')
            self.assertNotIn("SkillsAPI", stripped)
            self.assertIn("b = 1;", stripped)

    def test_dependency_after_such_a_string_is_found(self):
        mod = self.mod({"P.cs": PLUGIN % 'void F(string r) { var a = $@"{r}\\"; SkillsAPI.AddSkill(typeof(P)); }'})
        self.assertIn("Skills", core.audit_project(mod)["r2api_modules"])


class MalformedInputTests(Fixture):
    def _manifest(self, mod, value):
        (mod / "package/manifest.json").write_text(value if isinstance(value, str) else json.dumps(value),
                                                   encoding="utf-8")

    def test_dependencies_that_are_not_strings_are_reported_not_raised(self):
        mod = self.mod({"P.cs": PLUGIN % ""})
        self._manifest(mod, {"name": "AuditMod", "version_number": "1.0.0", "dependencies": [1, None, "bad"]})
        result = core.audit_project(mod)
        self.assertFalse(result["valid"])
        self.assertTrue(any("Team-Package-Version" in e for e in result["errors"]), result["errors"])

    def test_dependencies_that_are_not_a_list_are_reported_not_raised(self):
        mod = self.mod({"P.cs": PLUGIN % ""})
        self._manifest(mod, {"name": "AuditMod", "version_number": "1.0.0", "dependencies": None})
        self.assertTrue(any("dependencies" in e for e in core.audit_project(mod)["errors"]))

    def test_manifest_that_is_not_an_object_is_a_clear_error(self):
        mod = self.mod({"P.cs": PLUGIN % ""})
        self._manifest(mod, "[1]")
        with self.assertRaisesRegex(ValueError, "manifest.json must be a JSON object"):
            core.audit_project(mod)

    def test_manifest_that_is_not_json_is_a_clear_error(self):
        mod = self.mod({"P.cs": PLUGIN % ""})
        self._manifest(mod, "{")
        with self.assertRaisesRegex(ValueError, "manifest.json is not valid JSON"):
            core.audit_project(mod)

    def test_event_map_paths_outside_the_package_are_reported_not_raised(self):
        mod = self.mod({"P.cs": PLUGIN % ""}, events="Play_a=C:/x.wav\nPlay_b=../y.wav\nPlay_c=[z.wav\nPlay_d=clip.wav\n")
        errors = core.audit_project(mod)["errors"]
        for asset in ("C:/x.wav", "../y.wav", "[z.wav"):
            self.assertTrue(any(asset in e for e in errors), (asset, errors))
        self.assertFalse(any("clip.wav" in e for e in errors), errors)

    def test_malformed_csproj_is_reported_not_raised(self):
        mod = self.mod({"P.cs": PLUGIN % ""})
        (mod / "src/AuditMod.csproj").write_text("<Project><Version>1.0.0</Project>", encoding="utf-8")
        errors = core.audit_project(mod)["errors"]
        self.assertTrue(any("AuditMod.csproj is not valid XML" in e for e in errors), errors)


class ManifestSelectionTests(Fixture):
    def test_a_shallower_json_that_is_not_a_package_manifest_is_not_chosen(self):
        # Found on a shipped survivor: tools/hashes/manifest.json (a hash-table index) sat one level above the real
        # package manifest and produced 13 false errors.
        mod = self.mod({"P.cs": PLUGIN % ""}, deps=["RiskofThunder-R2API_Core-5.3.0"])
        (mod / "manifest.json").write_text(json.dumps({"schema": 1, "tables": {}}), encoding="utf-8")
        result = core.audit_project(mod)
        self.assertTrue(result["manifest"].endswith("package\\manifest.json") or
                        result["manifest"].endswith("package/manifest.json"), result["manifest"])

    def test_installed_packages_in_a_dev_profile_are_never_the_mod(self):
        mod = self.mod({"P.cs": PLUGIN % ""})
        other = mod / "devprofile/BepInEx/plugins/Other"
        other.mkdir(parents=True)
        (other / "manifest.json").write_text(json.dumps({"name": "Other", "version_number": "9.9.9",
                                                         "dependencies": []}), encoding="utf-8")
        (mod / "package/manifest.json").rename(mod / "src/deep_manifest_holder.json")
        (mod / "src/a/b/c").mkdir(parents=True)
        (mod / "src/deep_manifest_holder.json").rename(mod / "src/a/b/c/manifest.json")
        self.assertIn("src", core.audit_project(mod)["manifest"])


class ReferenceFolderTests(Fixture):
    def test_reference_projects_are_not_audited_as_this_mods_source(self):
        mod = self.mod({"P.cs": PLUGIN % ""})
        tutorial = mod / "references/HenryTutorial/Modules"
        tutorial.mkdir(parents=True)
        (tutorial / "Prefabs.cs").write_text('class X { string s = "Play_player_footstep"; }', encoding="utf-8")
        (mod / "content/assets").mkdir(parents=True)
        (mod / "content/assets/events.txt").write_text("", encoding="utf-8")
        self.assertTrue(core.audit_project(mod)["valid"])

    def test_a_project_whose_own_path_contains_references_still_audits(self):
        nested = self.root / "references" / "work"
        nested.mkdir(parents=True)
        self.root = nested
        mod = self.mod({"P.cs": PLUGIN % ""})
        self.assertEqual(core.audit_project(mod)["sources"], 1)


class PackageWithoutBuildTests(Fixture):
    def test_packaging_before_a_build_says_so(self):
        (self.root / "templates").mkdir()
        for name in ("plugin.cs",):
            (self.root / "templates" / name).write_text((core.PACKAGE_ROOT / "templates" / name).read_text(encoding="utf-8"),
                                                        encoding="utf-8")
        with patch.object(core, "ROOT", self.root):
            core.new_mod("Unbuilt", "Team")
            with self.assertRaisesRegex(ValueError, "forge build Unbuilt"):
                core.package_mod("Unbuilt")


class CiEvidenceTests(Fixture):
    REQUIRED = ["Windows tests and mod builds", "Analyze (actions)", "Analyze (csharp)", "Analyze (python)"]

    def _state(self, runs):
        payload = json.dumps({"check_runs": runs})
        with patch.object(core, "_repo_slug", return_value="o/r"), \
                patch.object(core.subprocess, "run",
                             return_value=subprocess.CompletedProcess([], 0, payload, "")):
            return core._ci_state("abc123")

    def _runs(self, **override):
        runs = [{"name": name, "status": "completed", "conclusion": "success"} for name in self.REQUIRED]
        for run in runs:
            if run["name"] in override:
                run.update(override[run["name"]])
        return runs

    def test_all_four_required_checks_verify(self):
        state, names = self._state(self._runs())
        self.assertEqual(state, "verified")
        self.assertEqual(len(names), 4)

    def test_a_failed_code_scan_fails_the_gate(self):
        state, _ = self._state(self._runs(**{"Analyze (python)": {"conclusion": "failure"}}))
        self.assertEqual(state, "failed")

    def test_a_missing_code_scan_is_not_verified(self):
        runs = [run for run in self._runs() if run["name"] != "Analyze (csharp)"]
        state, names = self._state(runs)
        self.assertEqual(state, "unknown")
        self.assertIn("Analyze (csharp):missing", names)

    def test_a_running_code_scan_is_pending(self):
        state, _ = self._state(self._runs(**{"Analyze (actions)": {"status": "in_progress", "conclusion": None}}))
        self.assertEqual(state, "pending")

    def test_required_checks_match_the_protected_branch(self):
        self.assertEqual(sorted(core.REQUIRED_CHECKS), sorted(self.REQUIRED))


class RequireVerifiedTests(Fixture):
    def test_unverified_release_fails_when_verification_is_required(self):
        (self.root / "VERSION").write_text("1.2.3\n", encoding="utf-8")
        (self.root / "CHANGELOG.md").write_text("# 1.2.3 — x\n", encoding="utf-8")

        def fake(args, **kwargs):
            return subprocess.CompletedProcess(args, 0, "v1.2.3", "")

        with patch.object(core, "ROOT", self.root), patch("ror2forge.__version__", "1.2.3"), \
                patch.object(core.subprocess, "run", side_effect=fake):
            relaxed = core.release_check("release")
            strict = core.release_check("release", require_verified=True)
        self.assertTrue(relaxed["valid"])
        self.assertFalse(strict["valid"])
        self.assertTrue(any("not verified" in e for e in strict["errors"]), strict["errors"])


class GuideTopicTests(Fixture):
    def test_task_routing_and_toolchain_are_guide_topics(self):
        for topic, marker in (("tasks", "forge plan"), ("toolchain", "ilspycmd")):
            self.assertIn(marker, core.guide(topic)["text"])
