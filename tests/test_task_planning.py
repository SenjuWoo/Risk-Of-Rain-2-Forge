"""Task-aware guidance and per-frame findings: the agent gets the right docs, and only warnings that mean something."""
import pathlib
import tempfile
import unittest

from ror2forge import core, tasks

ROOT = core.PACKAGE_ROOT


class PlanTests(unittest.TestCase):
    def test_simple_stat_request_stays_small(self):
        plan = tasks.plan("Make Commando deal 10% more damage")
        self.assertEqual(plan["categories"], ["stats"], plan)
        self.assertIn("R2API.RecalculateStats", plan["required"])
        self.assertNotIn("docs/CHARACTER_PIPELINE.md", plan["docs"])
        self.assertNotIn("AssetBundles", " ".join(plan["required"]))
        self.assertIn("AssetBundles", " ".join(plan["avoid"]))

    def test_survivor_request_pulls_the_character_route(self):
        plan = tasks.plan("Create a new playable survivor with 20 skins, custom attacks, a flying companion and "
                          "special effects")
        self.assertIn("survivor", plan["categories"])
        self.assertIn("docs/CHARACTER_PIPELINE.md", plan["docs"])
        self.assertLessEqual(len(plan["docs"]), tasks.MAX_DOCS)
        self.assertIn("R2API.Skins", plan["required"])
        self.assertTrue(any("skin" in check for check in plan["checks"]), plan["checks"])

    def test_procedural_hazard_selects_geometry_not_survivors(self):
        plan = tasks.plan("Create a procedurally generated environmental hazard")
        self.assertIn("procedural", plan["categories"])
        self.assertNotIn("survivor", plan["categories"])
        self.assertFalse(any("Skins" in dep for dep in plan["required"]))

    def test_networking_request_is_flagged(self):
        plan = tasks.plan("Add a multiplayer feature that syncs a buff to clients on late join")
        self.assertIn("networking", plan["categories"])
        self.assertTrue(any("host and client" in check for check in plan["checks"]), plan["checks"])

    def test_docs_are_capped_and_ordered(self):
        plan = tasks.plan("new survivor with skins, custom attacks, a companion, vfx and a network sync")
        self.assertLessEqual(len(plan["docs"]), tasks.MAX_DOCS)
        for doc in plan["docs"]:
            self.assertTrue((ROOT / doc).is_file(), doc)

    def test_audio_survives_a_crowded_request(self):
        plan = tasks.plan("Create a survivor with complex multiplayer projectile effects, 12 skins, animations "
                          "and audio")
        self.assertIn("audio", plan["categories"])
        self.assertIn("docs/AUDIO.md", plan["primary_docs"])
        self.assertIn("docs/AUDIO.md", plan["docs"])

    def test_every_chosen_category_keeps_its_own_document(self):
        plan = tasks.plan("Create a survivor with complex multiplayer projectile effects, 12 skins, animations "
                          "and audio")
        for category in plan["categories"]:
            self.assertIn(tasks.CATEGORIES[category]["docs"][0], plan["primary_docs"], category)

    def test_projectile_heavy_multiplayer_request(self):
        plan = tasks.plan("A projectile-heavy weapon for multiplayer with synced effects")
        self.assertIn("projectile", plan["categories"])
        self.assertIn("networking", plan["categories"])
        self.assertTrue(any("server" in check or "authority" in check for check in plan["checks"]))

    def test_crowded_request_reports_what_it_excluded(self):
        plan = tasks.plan("survivor with skins, custom attacks, a companion, projectiles, stage hazard, vfx, "
                          "audio and multiplayer sync")
        self.assertEqual(len(plan["categories"]), 3)
        self.assertTrue(plan["excluded"], plan)
        self.assertTrue(all("category" in row for row in plan["excluded"]))
        self.assertLessEqual(len(plan["docs"]), tasks.MAX_DOCS)

    def test_unmatched_request_is_honest(self):
        plan = tasks.plan("do something interesting")
        self.assertEqual(plan["categories"], [])
        self.assertIn("docs/RECIPES.md", plan["docs"])


class FindingBudgetTests(unittest.TestCase):
    def audit(self, limit):
        with tempfile.TemporaryDirectory(dir=ROOT / "artifacts") as scratch:
            root = pathlib.Path(scratch)
            (root / "manifest.json").write_text(
                '{"name":"Many","version_number":"1.0.0","website_url":"","description":"d","dependencies":[]}',
                encoding="utf-8")
            (root / "src").mkdir()
            lines = ["class P {", "  void Update() {"]
            lines += ["    var o%d = FindObjectsOfType<Enemy>();" % i for i in range(15)]
            lines += ["  }", "}"]
            (root / "src/P.cs").write_text("\n".join(lines) + "\n", encoding="utf-8")
            return core.audit_project(root, findings_limit=limit)

    def test_total_is_exact_and_truncation_is_explicit(self):
        result = self.audit(12)
        self.assertEqual(result["findings_total"], 15)
        self.assertTrue(result["findings_truncated"])
        self.assertEqual(len(result["findings"]), 12)
        self.assertEqual(len(result["warnings"]), 13, result["warnings"])
        self.assertTrue(result["warnings"][-1].startswith("15 per-frame findings"))
        self.assertIn("--findings-limit 15", result["warnings"][-1])

    def test_limit_can_be_raised_without_changing_the_count(self):
        result = self.audit(20)
        self.assertEqual(result["findings_total"], 15)
        self.assertFalse(result["findings_truncated"])
        self.assertEqual(len(result["findings"]), 15)
        self.assertFalse(any("per-frame findings" in warning for warning in result["warnings"]))


class HotPathTests(unittest.TestCase):
    def findings(self, source):
        return core.hot_path_findings(source, "P.cs")

    def test_scene_search_in_update_is_flagged_with_a_line(self):
        source = "class P {\n  void Update() {\n    var e = FindObjectsOfType<Enemy>();\n  }\n}"
        hits = self.findings(source)
        self.assertEqual(len(hits), 1, hits)
        self.assertEqual(hits[0]["line"], 3)
        self.assertEqual(hits[0]["severity"], "warning")

    def test_physics_in_fixed_update_is_not_a_problem(self):
        self.assertEqual(self.findings("class P {\n  void FixedUpdate() { rb.velocity = v; }\n}"), [])

    def test_a_comment_or_string_does_not_trip_it(self):
        source = ("class P {\n  void Update() {\n    // GameObject.Find was removed\n"
                  "    var s = \"GameObject.Find(x)\";\n  }\n}")
        self.assertEqual(self.findings(core._strip_csharp(source)), [])

    def test_linq_in_update_is_a_lower_confidence_warning(self):
        hits = self.findings("class P {\n  void LateUpdate() {\n    var x = list.Where(v => v).ToList();\n  }\n}")
        self.assertEqual(len(hits), 1, hits)
        self.assertEqual(hits[0]["confidence"], "medium")

    def test_findings_reach_the_audit_payload(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "artifacts") as scratch:
            root = pathlib.Path(scratch)
            (root / "manifest.json").write_text(
                '{"name":"Hot","version_number":"1.0.0","website_url":"","description":"d","dependencies":[]}',
                encoding="utf-8")
            (root / "src").mkdir()
            (root / "src/P.cs").write_text(
                "class P {\n  void Update() {\n    var e = FindObjectsOfType<Enemy>();\n  }\n}\n", encoding="utf-8")
            result = core.audit_project(root)
        self.assertTrue(result["findings"], result["warnings"])
        self.assertEqual(result["findings"][0]["file"], "P.cs")
        self.assertTrue(any("FindObjectsOfType" in warning for warning in result["warnings"]))


if __name__ == "__main__":
    unittest.main()
