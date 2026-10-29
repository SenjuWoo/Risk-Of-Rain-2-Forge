"""Toolchain cache checks; no network, runtime installation, or global writes."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from ror2forge import toolchain
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
        self.assertEqual(env["PIP_CACHE_DIR"], str(root.resolve() / "tools/cache/pip"))
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

    def stale_cache(self, root):
        (root / "WORKSPACE_OWNERSHIP.md").write_text("fixture")
        wheels = root / "tools/cache/wheels"
        wheels.mkdir(parents=True)
        self.wheel(wheels, "2.2.0")
        lock = wheels.parent / "python-requirements.lock"
        lock.write_text(_wheel_lock(wheels))
        environment = root / ".venv/working.txt"
        environment.parent.mkdir()
        environment.write_bytes(b"working environment")
        return lock, wheels, environment

    def wheel(self, directory, version):
        wheel = directory / f"mcp-{version}-py3-none-any.whl"
        with zipfile.ZipFile(wheel, "w") as archive:
            archive.writestr(f"mcp-{version}.dist-info/METADATA", f"Name: mcp\nVersion: {version}\n")

    def test_stale_offline_lock_fails_before_install_or_venv_mutation(self):
        with self.temporary() as temporary:
            root = Path(temporary)
            lock, wheels, environment = self.stale_cache(root)
            before = lock.read_bytes()
            with patch.object(toolchain, "_run", return_value="10.0.403") as run, patch.object(toolchain.shutil, "which", return_value="dotnet"):
                with self.assertRaisesRegex(RuntimeError, "stale Python lock"):
                    setup(root, offline=True)
            self.assertEqual(run.call_args_list[0].args[0], ["dotnet", "--version"])
            self.assertEqual(run.call_count, 1)
            self.assertEqual(lock.read_bytes(), before)
            self.assertTrue((wheels / "mcp-2.2.0-py3-none-any.whl").is_file())
            self.assertEqual(environment.read_bytes(), b"working environment")

    def test_failed_online_download_preserves_working_cache_and_environment(self):
        with self.temporary() as temporary:
            root = Path(temporary)
            lock, wheels, environment = self.stale_cache(root)
            before = lock.read_bytes()
            def fail_download(*args, **kwargs):
                raise RuntimeError("download failed")
            with patch.object(toolchain, "_python_ready", return_value=True), patch.object(toolchain, "_run", side_effect=fail_download):
                with self.assertRaisesRegex(RuntimeError, "download failed"):
                    toolchain._prepare_python_cache(root, False)
            self.assertEqual(lock.read_bytes(), before)
            self.assertEqual([item.name for item in wheels.iterdir()], ["mcp-2.2.0-py3-none-any.whl"])
            self.assertEqual(environment.read_bytes(), b"working environment")

    def test_changed_pin_download_uses_clean_wheels_and_preserves_previous_cache(self):
        with self.temporary() as temporary:
            root = Path(temporary)
            lock, wheels, environment = self.stale_cache(root)
            before = lock.read_bytes()
            def download(args, *a, **kw):
                destination = Path(args[args.index("--dest") + 1])
                self.assertEqual(list(destination.iterdir()), [])
                self.wheel(destination, toolchain.MCP_VERSION)
                return "downloaded"
            with patch.object(toolchain, "_python_ready", return_value=True), patch.object(toolchain, "_run", side_effect=download):
                toolchain._prepare_python_cache(root, False)
            self.assertEqual(toolchain._locked_mcp(lock.read_text()), toolchain.MCP_VERSION)
            self.assertFalse((wheels / "mcp-2.2.0-py3-none-any.whl").exists())
            backup = next((lock.parent / "backups").iterdir())
            self.assertEqual((backup / lock.name).read_bytes(), before)
            self.assertTrue((backup / "wheels/mcp-2.2.0-py3-none-any.whl").is_file())
            self.assertEqual(environment.read_bytes(), b"working environment")

    def test_cache_swap_failure_restores_previous_lock_and_wheels(self):
        with self.temporary() as temporary:
            root = Path(temporary)
            lock, wheels, environment = self.stale_cache(root)
            before = lock.read_bytes()
            original_replace = toolchain.os.replace
            calls = 0
            def fail_fourth(source, target):
                nonlocal calls
                calls += 1
                if calls == 4:
                    raise OSError("swap failed")
                return original_replace(source, target)
            def download(args, *a, **kw):
                self.wheel(Path(args[args.index("--dest") + 1]), toolchain.MCP_VERSION)
                return "downloaded"
            with patch.object(toolchain, "_python_ready", return_value=True), patch.object(toolchain, "_run", side_effect=download), patch.object(toolchain.os, "replace", side_effect=fail_fourth):
                with self.assertRaisesRegex(OSError, "swap failed"):
                    toolchain._prepare_python_cache(root, False)
            self.assertEqual(lock.read_bytes(), before)
            self.assertEqual([item.name for item in wheels.iterdir()], ["mcp-2.2.0-py3-none-any.whl"])
            self.assertEqual(environment.read_bytes(), b"working environment")

    def test_matching_lock_does_not_download(self):
        with self.temporary() as temporary:
            root = Path(temporary)
            lock = root / "tools/cache/python-requirements.lock"
            lock.parent.mkdir(parents=True)
            lock.write_text(f"mcp=={toolchain.MCP_VERSION} --hash=sha256:fixture\n")
            with patch.object(toolchain, "_run") as run:
                toolchain._prepare_python_cache(root, True)
            run.assert_not_called()

    def environment_fixture(self, root):
        (root / "WORKSPACE_OWNERSHIP.md").write_text("fixture")
        lock = root / "tools/cache/python-requirements.lock"
        lock.parent.mkdir(parents=True)
        lock.write_text(f"mcp=={toolchain.MCP_VERSION} --hash=sha256:fixture\n")
        python = Path(tool_paths(root)["python"])
        python.parent.mkdir(parents=True)
        python.touch()

    def fake_installed_command(self, args, *a, **kw):
        if args[1:3] == ["tool", "list"]:
            return "\n".join(f"{name} {version} {name}" for name, version in toolchain.DOTNET_TOOLS.items())
        if args[-1] == "import importlib.metadata; print(importlib.metadata.version('mcp'))":
            return toolchain.MCP_VERSION
        if args[-1] == "--version":
            executable = Path(args[0]).stem
            if executable == "ilspycmd":
                return f"ilspycmd: {toolchain.DOTNET_TOOLS['ilspycmd']}"
            if executable == "tcli":
                return f"tcli {toolchain.DOTNET_TOOLS['tcli']}"
            return "10.0.403"
        return ""

    def test_healthy_environment_is_not_recreated(self):
        with self.temporary() as temporary:
            root = Path(temporary)
            self.environment_fixture(root)
            with patch.object(toolchain.shutil, "which", return_value="dotnet"), patch.object(toolchain, "_python_ready", return_value=True), patch.object(toolchain, "_run", side_effect=self.fake_installed_command) as run:
                setup(root, offline=True)
            self.assertFalse(any("venv" in call.args[0] for call in run.call_args_list))

    def test_interrupted_pip_is_repaired(self):
        with self.temporary() as temporary:
            root = Path(temporary)
            self.environment_fixture(root)
            with patch.object(toolchain.shutil, "which", return_value="dotnet"), patch.object(toolchain, "_python_ready", return_value=False), patch.object(toolchain, "_run", side_effect=self.fake_installed_command) as run:
                setup(root, offline=True)
            self.assertTrue(any("venv" in call.args[0] for call in run.call_args_list))


if __name__ == "__main__":
    unittest.main()
