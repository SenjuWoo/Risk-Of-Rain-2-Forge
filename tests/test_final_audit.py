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


class ReleaseModeTests(Fixture):
    def _project(self, version="1.2.3", changelog="# 1.2.3 — x\n"):
        (self.root / "VERSION").write_text(version + "\n", encoding="utf-8")
        if changelog is not None:
            (self.root / "CHANGELOG.md").write_text(changelog, encoding="utf-8")

    def _git(self, returncode=0, stdout="", stderr="", raises=None, head="deadbeef"):
        def fake(args, **kwargs):
            if raises:
                raise raises
            if "rev-parse" in args:
                return subprocess.CompletedProcess(args, 0, head, "")
            return subprocess.CompletedProcess(args, returncode, stdout, stderr)
        return patch.object(core.subprocess, "run", side_effect=fake)

    def test_prerelease_allows_no_tag(self):
        self._project()
        with patch.object(core, "ROOT", self.root), patch("ror2forge.__version__", "1.2.3"), \
                self._git(returncode=1):
            result = core.release_check("prerelease")
        self.assertTrue(result["valid"], result["errors"])
        self.assertEqual(result["tag_status"], "not_required")

    def test_release_requires_a_tag(self):
        self._project()
        with patch.object(core, "ROOT", self.root), patch("ror2forge.__version__", "1.2.3"), \
                self._git(returncode=1):
            result = core.release_check("release")
        self.assertFalse(result["valid"])
        self.assertIn("no version tag", result["errors"][0])

    def test_missing_changelog_fails_even_in_prerelease(self):
        self._project(changelog=None)
        with patch.object(core, "ROOT", self.root), patch("ror2forge.__version__", "1.2.3"), \
                self._git(returncode=1):
            result = core.release_check("prerelease")
        self.assertFalse(result["valid"])
        self.assertIn("CHANGELOG.md is missing", result["errors"])

    def test_stale_tag_on_a_development_branch_warns_not_fails(self):
        self._project()
        with patch.object(core, "ROOT", self.root), patch("ror2forge.__version__", "1.2.3"),                 self._git(stdout="v1.2.2"):
            result = core.release_check("prerelease")
        self.assertTrue(result["valid"], result["errors"])
        self.assertEqual(result["tag_status"], "stale")
        self.assertTrue(any("!= VERSION" in w for w in result["warnings"]))

    def test_malformed_and_mismatched_tags(self):
        self._project()
        for tag, fragment in (("vv1.2.3", "single-v"), ("v1.2.2", "!= VERSION")):
            with self.subTest(tag=tag):
                with patch.object(core, "ROOT", self.root), patch("ror2forge.__version__", "1.2.3"), \
                        self._git(stdout=tag):
                    result = core.release_check("release")
                self.assertFalse(result["valid"])
                self.assertTrue(any(fragment in e for e in result["errors"]), result["errors"])

    def test_git_unavailable_fails_a_release_and_warns_a_prerelease(self):
        self._project()
        with patch.object(core, "ROOT", self.root), patch("ror2forge.__version__", "1.2.3"), \
                self._git(raises=FileNotFoundError("git")):
            release = core.release_check("release")
            prerelease = core.release_check("prerelease")
        self.assertFalse(release["valid"])
        self.assertFalse(prerelease["verified"])
        self.assertTrue(any("git unavailable" in w for w in prerelease["warnings"]))

    def _publish(self, head="deadbeef"):
        """A release folder shaped like a real one: source zip, receipt with artifact+ci, sums."""
        assets = self.root / "assets"
        assets.mkdir(exist_ok=True)
        zip_path = assets / "kit-source.zip"
        zip_path.write_bytes(b"release bytes")
        receipt = {"commit": head, "artifact": {"file": "kit-source.zip", "sha256": core.sha256(zip_path),
                                                "size_bytes": zip_path.stat().st_size},
                   "ci_checks": [{"name": "CI", "conclusion": "success"}]}
        (assets / "BUILD-RECEIPT.json").write_text(json.dumps(receipt), encoding="utf-8")
        rows = [
            f"{core.sha256(zip_path)}  kit-source.zip",
            f"{core.sha256(assets / 'BUILD-RECEIPT.json')}  BUILD-RECEIPT.json",
            "",
        ]
        (assets / "SHA256SUMS").write_text(chr(10).join(rows), encoding="utf-8")
        return assets

    def _release(self, assets, head="deadbeef"):
        with patch.object(core, "ROOT", self.root), patch("ror2forge.__version__", "1.2.3"),                 self._git(stdout="v1.2.3", head=head):
            return core.release_check("release", assets)

    def test_complete_assets_verify(self):
        self._project()
        result = self._release(self._publish())
        self.assertTrue(result["release_verified"], result["errors"])
        self.assertTrue(result["checks"]["assets"])

    def test_empty_checksum_file_fails(self):
        self._project()
        assets = self._publish()
        (assets / "SHA256SUMS").write_text("", encoding="utf-8")
        result = self._release(assets)
        self.assertFalse(result["release_verified"])
        self.assertIn("lists no files", " ".join(result["errors"]))

    def test_missing_source_zip_fails(self):
        self._project()
        assets = self._publish()
        (assets / "kit-source.zip").unlink()
        self.assertFalse(self._release(assets)["release_verified"])

    def test_receipt_with_only_a_commit_is_incomplete(self):
        self._project()
        assets = self._publish()
        (assets / "BUILD-RECEIPT.json").write_text(json.dumps({"commit": "deadbeef"}), encoding="utf-8")
        result = self._release(assets)
        self.assertFalse(result["release_verified"])
        self.assertTrue(any("artifact is missing" in e for e in result["errors"]))

    def test_tampered_zip_fails(self):
        self._project()
        assets = self._publish()
        (assets / "kit-source.zip").write_bytes(b"tampered")
        self.assertFalse(self._release(assets)["release_verified"])

    def test_duplicate_and_traversal_entries_fail(self):
        self._project()
        assets = self._publish()
        good = core.sha256(assets / "kit-source.zip")
        (assets / "SHA256SUMS").write_text(chr(10).join([f"{good}  kit-source.zip"] * 2) + chr(10), encoding="utf-8")
        self.assertFalse(self._release(assets)["release_verified"])
        (assets / "SHA256SUMS").write_text(f"{good}  ../escape.zip" + chr(10), encoding="utf-8")
        self.assertFalse(self._release(assets)["release_verified"])

    def test_wrong_receipt_commit_fails(self):
        self._project()
        assets = self._publish(head="cafebabe")
        result = self._release(assets, head="cafebabe")
        self.assertTrue(result["release_verified"], result["errors"])
        result = self._release(assets, head="deadbeef")
        self.assertFalse(result["release_verified"])

    def test_no_assets_means_not_release_verified(self):
        self._project()
        with patch.object(core, "ROOT", self.root), patch("ror2forge.__version__", "1.2.3"),                 self._git(stdout="v1.2.3"):
            result = core.release_check("release")
        self.assertFalse(result["release_verified"])
        self.assertFalse(result["checks"]["assets"])
        self.assertTrue(any("--assets" in w for w in result["warnings"]))


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
