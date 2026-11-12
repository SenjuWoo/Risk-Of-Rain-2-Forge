"""Audit false positives found on a real survivor: literal volume reads, qualified R2API.Utils, assets/audio maps, run-once lookups."""
from test_final_audit import Fixture
from ror2forge import core

CORE = ["RiskofThunder-R2API_Core-5.3.0"]


class LayoutTests(Fixture):
    def test_volume_read_as_a_string_literal_counts(self):
        mod = self.mod({"Audio.cs": "class A { void P() { waveOutWrite(h, p, 32); } }",
                        "Wrap.cs": 'class W { float V() => ReadConVar(console, "volume_sfx"); }'}, deps=CORE)
        self.assertFalse(any("SFX volume" in w for w in core.audit_project(mod)["warnings"]))

    def test_qualified_r2api_utils_maps_to_core(self):
        mod = self.mod({"P.cs": "[R2API.Utils.NetworkCompatibility(CompatibilityLevel.EveryoneMustHaveMod)] class P {}"}, deps=CORE)
        result = core.audit_project(mod)
        self.assertTrue(result["valid"], result["errors"])
        self.assertFalse(any("unresolved" in w for w in result["warnings"]), result["warnings"])

    def test_qualified_r2api_utils_still_needs_core(self):
        mod = self.mod({"P.cs": "[R2API.Utils.NetworkCompatibility(CompatibilityLevel.EveryoneMustHaveMod)] class P {}"})
        self.assertFalse(core.audit_project(mod)["valid"])

    def _assets_audio_map(self, listed):
        mod = self.mod({"A.cs": 'class P { void M(){ Play("Play_Custom"); Play("Play_Missing"); } }'})
        audio = mod / "package" / "assets" / "audio"
        audio.mkdir(parents=True)
        (audio / "events.txt").write_text(f"Play_Custom={listed}\n", encoding="utf-8")
        (audio / "clip.wav").write_bytes(b"RIFF")
        return core.audit_project(mod)["errors"]

    def test_assets_audio_map_without_content_dir_is_shipped_and_checked(self):
        errors = self._assets_audio_map("clip.wav")
        self.assertFalse(any("outside content/" in e for e in errors), errors)
        self.assertTrue(any("Play_Missing" in e for e in errors), errors)  # key check now runs for this layout

    def test_assets_audio_map_listing_a_missing_file_is_reported(self):
        self.assertTrue(any("gone.wav" in e for e in self._assets_audio_map("gone.wav")))


class HotPathTests(Fixture):
    def test_getcomponent_is_medium_confidence(self):
        found = core.hot_path_findings("class A { void Update() { var r = GetComponent<Rigidbody>(); } }", "A.cs")
        self.assertEqual([f["confidence"] for f in found], ["medium"])

    def test_other_lookups_stay_high_confidence(self):
        found = core.hot_path_findings("class A { void Update() { var o = GameObject.Find(\"x\"); } }", "A.cs")
        self.assertEqual([f["confidence"] for f in found], ["high"])

    def test_run_once_guarded_lookup_is_skipped(self):
        src = "class A { bool b; void Update() { if (!b) { b = true; var r = GetComponent<Rigidbody>(); } } }"
        self.assertEqual(core.hot_path_findings(src, "A.cs"), [])

    def test_unguarded_lookup_in_a_different_if_is_still_flagged(self):
        src = "class A { bool b; void Update() { if (!b) { Foo(); } var r = GetComponent<Rigidbody>(); } }"
        self.assertEqual(len(core.hot_path_findings(src, "A.cs")), 1)

    def test_guard_that_never_sets_the_flag_is_still_flagged(self):
        src = "class A { bool b; void Update() { if (!b) { var r = GetComponent<Rigidbody>(); } } }"
        self.assertEqual(len(core.hot_path_findings(src, "A.cs")), 1)

    def test_run_once_guard_with_extra_condition_is_skipped(self):
        src = "class A { bool done; float t; void FixedUpdate() { if (!done && t >= 1f) { done = true; var r = GetComponent<Rigidbody>(); } } }"
        self.assertEqual(core.hot_path_findings(src, "A.cs"), [])

    def test_or_condition_is_not_treated_as_a_run_once_guard(self):
        src = "class A { bool done; bool x; void Update() { if (!done || x) { done = true; var r = GetComponent<Rigidbody>(); } } }"
        self.assertEqual(len(core.hot_path_findings(src, "A.cs")), 1)
