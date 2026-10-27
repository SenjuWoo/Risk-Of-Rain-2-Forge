"""Toolchain cache checks; no network, runtime installation, or global writes."""
import hashlib
from pathlib import Path
import tempfile
import unittest
import zipfile

from ror2forge.toolchain import ROOT, _cache_packages, _wheel_lock, dotnet_env, setup, tool_paths


class ToolchainTests(unittest.TestCase):
    def temporary(self):
        directory = ROOT / "tools/cache/test-temp"
        directory.mkdir(parents=True, exist_ok=True)
        return tempfile.TemporaryDirectory(dir=directory)

    def test_local_environment_preserves_parent_and_scopes_caches(self):
        root = Path(tempfile.gettempdir()) / "forge tools"
        env = dotnet_env(root)
        self.assertEqual(env["DOTNET_CLI_HOME"], str(root.resolve() / "tools/cache/dotnet-home"))
        self.assertEqual(env["DOTNET_GENERATE_ASPNET_CERTIFICATE"], "false")
        self.assertTrue(Path(tool_paths(root)["python"]).is_relative_to(root.resolve()))

    def test_wheel_lock_pins_names_versions_and_archive_hash(self):
        with self.temporary() as temporary:
            root = Path(temporary)
            wheel = root / "demo-1.2.3-py3-none-any.whl"
            with zipfile.ZipFile(wheel, "w") as archive:
                archive.writestr("demo-1.2.3.dist-info/METADATA", "Name: Demo\nVersion: 1.2.3\n")
            digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
            self.assertEqual(_wheel_lock(root), f"Demo==1.2.3 --hash=sha256:{digest}\n")

    def test_empty_cache_is_not_an_offline_success(self):
        with self.temporary() as temporary:
            with self.assertRaisesRegex(ValueError, "No cached wheels"):
                _wheel_lock(Path(temporary))

    def test_unowned_root_is_rejected_before_install(self):
        with self.temporary() as temporary:
            with self.assertRaisesRegex(ValueError, "owned forge root"):
                setup(Path(temporary))

    def test_existing_changed_nuget_cache_is_rejected(self):
        with self.temporary() as temporary:
            root = Path(temporary)
            store = root / "tools/bin/.store/demo"
            store.mkdir(parents=True)
            cache = root / "tools/cache/nuget"
            cache.mkdir(parents=True)
            with zipfile.ZipFile(store / "demo.nupkg", "w") as archive:
                archive.writestr("demo.nuspec", "<package><metadata><id>Demo</id><version>1.0.0</version><license>MIT</license></metadata></package>")
            packages = _cache_packages(root)
            self.assertEqual(packages[0]["license"], "MIT")
            (cache / "demo.1.0.0.nupkg").write_bytes(b"changed")
            with self.assertRaisesRegex(RuntimeError, "archive changed"):
                _cache_packages(root)

    def test_wheel_with_missing_metadata_is_rejected(self):
        with self.temporary() as temporary:
            root = Path(temporary)
            with zipfile.ZipFile(root / "invalid.whl", "w") as archive:
                archive.writestr("unexpected.txt", "not a wheel")
            with self.assertRaisesRegex(ValueError, "Invalid wheel metadata"):
                _wheel_lock(root)


if __name__ == "__main__":
    unittest.main()
