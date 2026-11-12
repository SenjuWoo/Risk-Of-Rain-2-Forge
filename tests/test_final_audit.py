"""Regression tests for the final audit: lexer, R2API ownership, release modes, build provenance, audio maps."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from ror2forge import core

REAL_ROOT = core.ROOT


class Fixture(unittest.TestCase):
    def setUp(self):
        area = REAL_ROOT / "artifacts/test-temp"
        area.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=area)
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def mod(self, files, deps=None, events=None):
        root = self.root / "mod"
        (root / "src").mkdir(parents=True, exist_ok=True)
        (root / "package").mkdir(parents=True, exist_ok=True)
        (root / "package" / "manifest.json").write_text(json.dumps({
            "name": "AuditMod", "version_number": "1.0.0", "website_url": "",
            "description": "x", "dependencies": deps or []}), encoding="utf-8")
        for name, text in files.items():
            (root / "src" / name).write_text(text, encoding="utf-8")
        if events is not None:
            assets = root / "content" / "assets"
            assets.mkdir(parents=True, exist_ok=True)
            (assets / "events.txt").write_text(events, encoding="utf-8")
            (assets / "clip.wav").write_bytes(b"RIFF")
        return root


class LexerTests(Fixture):
    def test_url_string_does_not_hide_the_event_after_it(self):
        mod = self.mod({"A.cs": 'class P { void M() { var url = "https://example.com"; Play("Play_Missing"); } }'},
                       events="# key=files\nPlay_Known=clip.wav\n")
        errors = core.audit_project(mod)["errors"]
        self.assertTrue(any("Play_Missing" in e for e in errors), errors)

    def test_escaped_quote_and_slashes_inside_a_string(self):
        source = r'class P { void M() { var s = "say \"/* not a comment */\" and // too"; Play("Play_Missing"); } }'
        mod = self.mod({"A.cs": source}, events="# key=files\nPlay_Known=clip.wav\n")
        self.assertTrue(any("Play_Missing" in e for e in core.audit_project(mod)["errors"]))

    def test_verbatim_string_with_doubled_quotes(self):
        source = 'class P { void M() { var s = @"he said ""/* x */"" // y"; Play("Play_Missing"); } }'
        mod = self.mod({"A.cs": source}, events="# key=files\nPlay_Known=clip.wav\n")
        self.assertTrue(any("Play_Missing" in e for e in core.audit_project(mod)["errors"]))

    def test_interpolated_and_verbatim_interpolated_strings(self):
        for prefix in ('$', '$@', '@$'):
            with self.subTest(prefix=prefix):
                source = f'class P {{ void M() {{ var s = {prefix}"x{{1}} // y"; Play("Play_Missing"); }} }}'
                mod = self.mod({"A.cs": source}, events="# key=files\nPlay_Known=clip.wav\n")
                self.assertTrue(any("Play_Missing" in e for e in core.audit_project(mod)["errors"]))

    def test_raw_string_is_one_literal(self):
        source = 'class P { void M() { var s = """Play_Fake // not an event"""; Play("Play_Missing"); } }'
        mod = self.mod({"A.cs": source}, events="# key=files\nPlay_Known=clip.wav\n")
        errors = core.audit_project(mod)["errors"]
        self.assertTrue(any("Play_Missing" in e for e in errors))
        self.assertFalse(any("Play_Fake" in e for e in errors), "text inside a raw string became an event")

    def test_block_comment_hides_a_fake_event_and_the_live_one_is_found(self):
        source = 'class P { /* Play("Play_Fake"); */ void M() { Play("Play_Known"); } }'
        mod = self.mod({"A.cs": source}, events="# key=files\nPlay_Known=clip.wav\n")
        result = core.audit_project(mod)
        self.assertTrue(result["valid"], result["errors"])

    def test_fake_dependency_in_comment_and_in_string(self):
        source = ('// [BepInDependency("com.bepis.r2api.skins")]\n'
                  'class P { string s = "[BepInDependency(\\"com.bepis.r2api.skins\\")]"; }')
        mod = self.mod({"A.cs": source})
        self.assertTrue(core.audit_project(mod)["valid"])

    def test_real_dependency_still_requires_its_package(self):
        mod = self.mod({"A.cs": '[BepInDependency("com.bepis.r2api.skins")]\nclass P {}'})
        self.assertFalse(core.audit_project(mod)["valid"])


class OwnershipTests(Fixture):
    def test_skillsapi_without_the_skills_package_fails(self):
        for source in ('class P { void M(){ R2API.SkillsAPI.SetCustomCooldownRefreshSound(s, "x"); } }',
                       'using R2API;\nclass P { void M(){ SkillsAPI.SetCustomCooldownRefreshSound(s, "x"); } }',
                       'using global::R2API;\nclass P { void M(){ R2API.SkillsAPI.X(); } }'):
            with self.subTest(source=source):
                mod = self.mod({"S.cs": source})
                result = core.audit_project(mod)
                self.assertFalse(result["valid"])
                self.assertIn("Skills", result["errors"][0])

    def test_skillsapi_with_the_package_passes(self):
        mod = self.mod({"S.cs": 'class P { void M(){ R2API.SkillsAPI.X(); } }'},
                       ["RiskofThunder-R2API_Skills-1.1.6"])
        self.assertTrue(core.audit_project(mod)["valid"])

    def test_unknown_r2api_name_is_reported_not_invented(self):
        mod = self.mod({"S.cs": 'class P { void M(){ R2API.MysteryAPI.X(); } }'})
        result = core.audit_project(mod)
        self.assertTrue(result["valid"], result["errors"])
        self.assertIn("MysteryAPI", result["r2api_unresolved"])
        self.assertTrue(any("unresolved" in w for w in result["warnings"]))

    def test_ownership_table_records_its_source(self):
        doc = core._OWNERSHIP
        self.assertEqual(doc["source"], "https://github.com/risk-of-thunder/R2API")
        self.assertIn("SkillsAPI", doc["types"])
        self.assertEqual(doc["types"]["SkillsAPI"], "Skills")

    def test_a_mod_declaring_its_own_class_is_not_an_r2api_reference(self):
        source = 'class SkillsAPI { }' + chr(10) + 'class P { void M(){ new SkillsAPI(); } }'
        self.assertTrue(core.audit_project(self.mod({'S.cs': source}))['valid'])

    def test_content_addition_requires_content_management(self):
        source = 'using R2API;' + chr(10) + 'class P { void M(){ ContentAddition.AddItemDef(x); } }'
        result = core.audit_project(self.mod({'S.cs': source}))
        self.assertFalse(result['valid'])
        self.assertIn('ContentManagement', result['errors'][0])

    def test_content_addition_passes_with_its_package(self):
        source = 'using R2API;' + chr(10) + 'class P { void M(){ ContentAddition.AddItemDef(x); } }'
        mod = self.mod({'S.cs': source}, ['RiskofThunder-R2API_ContentManagement-1.0.9'])
        self.assertTrue(core.audit_project(mod)['valid'])


class AudioMapTests(Fixture):
    def test_map_outside_content_is_reported(self):
        mod = self.mod({"A.cs": 'class P { void M(){ Play("Play_Custom"); } }'})
        (mod / "docs").mkdir()
        (mod / "docs" / "events.txt").write_text("Play_Custom=clip.wav\n", encoding="utf-8")
        errors = core.audit_project(mod)["errors"]
        self.assertTrue(any("outside content/" in e for e in errors), errors)

    def test_shipped_map_with_a_missing_asset_is_reported(self):
        mod = self.mod({"A.cs": 'class P { void M(){ Play("Play_Custom"); } }'},
                       events="Play_Custom=absent.wav\n")
        errors = core.audit_project(mod)["errors"]
        self.assertTrue(any("absent.wav" in e for e in errors), errors)


class GnarLayoutRegressionTests(Fixture):
    """Gnar 1.3.3 false positives: no content/ folder, qualified R2API.Utils, split audio files, one-shot lookups."""

    def _flat_audio_mod(self, source, events="Play_Real=clip.wav\n", clip=True):
        mod = self.mod({"A.cs": source}, ["RiskofThunder-R2API_Core-5.3.0"])
        audio = mod / "assets" / "audio"
        audio.mkdir(parents=True)
        (audio / "events.txt").write_text(events, encoding="utf-8")
        if clip:
            (audio / "clip.wav").write_bytes(b"RIFF")
        return mod

    def test_event_map_without_a_content_folder_ships_and_is_checked(self):
        mod = self._flat_audio_mod('class P { void M(){ Play("Play_Real"); } }')
        result = core.audit_project(mod)
        self.assertFalse(any("outside content/" in e for e in result["errors"]), result["errors"])
        self.assertEqual(result["errors"], [])

    def test_event_map_without_a_content_folder_still_checks_keys_and_files(self):
        mod = self._flat_audio_mod('class P { void M(){ Play("Play_Missing"); } }', clip=False)
        errors = core.audit_project(mod)["errors"]
        self.assertTrue(any("Play_Missing" in e for e in errors), errors)
        self.assertTrue(any("clip.wav" in e for e in errors), errors)

    def test_map_outside_content_is_still_an_error_when_content_exists(self):
        mod = self.mod({"A.cs": 'class P {}'}, events="Play_Real=clip.wav\n")
        (mod / "docs").mkdir()
        (mod / "docs" / "events.txt").write_text("Play_Other=clip.wav\n", encoding="utf-8")
        self.assertEqual(core.audit_project(mod)["errors"], [])      # the content/ map ships; docs/ is not a map
        for stale in (mod / "content").rglob("events.txt"):
            stale.unlink()
        self.assertTrue(any("outside content/" in e for e in core.audit_project(mod)["errors"]))

    def test_fully_qualified_utils_attribute_is_a_core_reference(self):
        source = "[R2API.Utils.NetworkCompatibility(R2API.Utils.CompatibilityLevel.EveryoneMustHaveMod)]\nclass P {}"
        mod = self.mod({"A.cs": source}, ["RiskofThunder-R2API_Core-5.3.0"])
        result = core.audit_project(mod)
        self.assertEqual(result["r2api_unresolved"], [])
        self.assertTrue(result["valid"], result["errors"])
        bare = self.mod({"A.cs": source}, [])
        self.assertTrue(any("R2API_Utils" in e or "Core" in e for e in core.audit_project(bare)["errors"]))

    def test_sfx_volume_read_by_convar_name_in_another_file_counts(self):
        mod = self.mod({"OsAudio.cs": "class O { void P(){ waveOutWrite(h, p, 32); } }",
                        "GnarAudio.cs": 'class G { float V(){ return Read(console, "volume_sfx"); } }'})
        self.assertFalse(any("SFX volume" in w for w in core.audit_project(mod)["warnings"]))

    def test_waveout_with_no_volume_read_anywhere_still_warns(self):
        mod = self.mod({"OsAudio.cs": "class O { void P(){ waveOutWrite(h, p, 32); } }"})
        self.assertTrue(any("SFX volume" in w for w in core.audit_project(mod)["warnings"]))

    def test_lookup_inside_a_one_shot_guard_is_not_per_frame(self):
        source = """class S { bool done;
          void FixedUpdate() { if (!done) { done = true; var r = body.GetComponent<Rage>(); } } }"""
        self.assertEqual(core.hot_path_findings(source, "S.cs"), [])

    def test_lookup_in_a_guard_that_never_latches_is_still_flagged(self):
        source = """class S { bool done;
          void FixedUpdate() { if (!done) { var r = body.GetComponent<Rage>(); } } }"""
        self.assertEqual(len(core.hot_path_findings(source, "S.cs")), 1)

    def test_unguarded_get_component_is_medium_confidence(self):
        found = core.hot_path_findings("class S { void Update() { var r = GetComponent<Rage>(); } }", "S.cs")
        self.assertEqual([f["confidence"] for f in found], ["medium"])
