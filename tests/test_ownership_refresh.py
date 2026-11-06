"""The ownership refresh must apply curated mappings, not merely persist them."""
import importlib.util
import pathlib
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts/refresh_r2api_ownership.py"


def load():
    spec = importlib.util.spec_from_file_location("refresh_ownership", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OwnershipRefreshTests(unittest.TestCase):
    def setUp(self):
        self.module = load()

    def test_curated_mapping_reaches_the_type_map(self):
        tree = {"tree": [{"path": "R2API.ContentManagement/ContentManagementAPI.cs"},
                         {"path": "R2API.ContentManagement/ContentAddition.cs"}]}
        types, modules = self.module.derive(tree, {"ContentAddition": "ContentManagement"})
        self.assertEqual(types["ContentAddition"], "ContentManagement")
        self.assertIn("ContentManagement", modules)

    def test_a_new_curated_entry_added_to_the_file_still_applies(self):
        tree = {"tree": [{"path": "R2API.Skins/SkinsAPI.cs"}]}
        types, _ = self.module.derive(tree, {"SkillsAPI": "Skills"})
        self.assertEqual(types["SkillsAPI"], "Skills")

    def test_non_api_helpers_never_become_types(self):
        tree = {"tree": [{"path": "R2API.Skins/Helpers.cs"}]}
        types, _ = self.module.derive(tree, {})
        self.assertNotIn("Helpers", types)

    def test_committed_map_matches_its_own_curated_section(self):
        import json
        data = json.loads((SCRIPT.parents[1] / "ror2forge/r2api_ownership.json").read_text(encoding="utf-8"))
        for name, module in data["curated"].items():
            self.assertEqual(data["types"].get(name), module, f"curated {name} is not applied")


if __name__ == "__main__":
    unittest.main()
