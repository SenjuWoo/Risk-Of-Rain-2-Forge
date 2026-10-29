"""Install the forge's official, pinned tools into this workspace.

Uses the existing Python and .NET runtimes; never installs either runtime.
Downloads and their hashes stay in tools/cache for repeatable offline setup.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile
from email.parser import BytesParser
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
DOTNET_TOOLS = {"ilspycmd": "11.2.0.10050", "tcli": "0.2.4"}
MCP_VERSION = (ROOT / "requirements-mcp.txt").read_text(encoding="utf-8").strip().removeprefix("mcp==")


def tool_paths(root: Path = ROOT) -> dict[str, str]:
    root = Path(root).resolve()
    suffix = ".exe" if os.name == "nt" else ""
    paths = {
        "ilspycmd": str(root / "tools" / "bin" / f"ilspycmd{suffix}"),
        "tcli": str(root / "tools" / "bin" / f"tcli{suffix}"),
        "python": str(root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")),
    }
    if os.name == "nt" and not Path(paths["ilspycmd"]).is_file():
        # .NET 10's RID-specific tool installs a cmd shim; use its native target.
        targets = list((root / "tools/bin/.store/ilspycmd" / DOTNET_TOOLS["ilspycmd"]).rglob("ilspycmd.exe"))
        if len(targets) > 1:
            raise RuntimeError("Multiple ILSpy native targets; resolve the local tool installation.")
        if targets:
            paths["ilspycmd"] = str(targets[0])
    return paths


def tool_command(name: str, root: Path = ROOT) -> list[str]:
    if name not in DOTNET_TOOLS:
        raise ValueError(f"Unknown forge tool: {name}")
    return [tool_paths(root)[name]]


def dotnet_env(root: Path = ROOT) -> dict[str, str]:
    cache = Path(root).resolve() / "tools" / "cache"
    return {
        **os.environ,
        "DOTNET_CLI_HOME": str(cache / "dotnet-home"),
        "NUGET_PACKAGES": str(cache / "packages"),
        "NUGET_HTTP_CACHE_PATH": str(cache / "http"),
        "PIP_CACHE_DIR": str(cache / "pip"),
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "TMP": str(cache / "tmp"),
        "TEMP": str(cache / "tmp"),
        "DOTNET_SKIP_FIRST_TIME_EXPERIENCE": "1",
        "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
        "DOTNET_NOLOGO": "1",
        "DOTNET_GENERATE_ASPNET_CERTIFICATE": "false",
    }


def _run(args: list[str], root: Path, *, timeout: int = 600,
         accepted_codes: tuple[int, ...] = (0,)) -> str:
    (root / "tools/cache/tmp").mkdir(parents=True, exist_ok=True)
    result = subprocess.run(args, cwd=root, env=dotnet_env(root), text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            timeout=timeout, check=False)
    if result.returncode not in accepted_codes:
        raise RuntimeError(f"{Path(args[0]).name} {' '.join(args[1:3])} failed ({result.returncode}):\n{result.stdout[-12000:]}")
    return result.stdout.strip()


def _hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _wheel_lock(wheels: Path) -> str:
    """Pin every transitive dependency to the downloaded wheel's exact bytes."""
    entries = []
    for wheel in sorted(wheels.glob("*.whl")):
        with zipfile.ZipFile(wheel) as archive:
            metadata = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
            if len(metadata) != 1:
                raise ValueError(f"Invalid wheel metadata: {wheel.name}")
            package = BytesParser().parsebytes(archive.read(metadata[0]))
        entries.append(f"{package['Name']}=={package['Version']} --hash=sha256:{_hash(wheel)}")
    if not entries:
        raise ValueError("No cached wheels; run setup online once on this Python/platform.")
    return "\n".join(entries) + "\n"


def _locked_mcp(text: str) -> str | None:
    pins = [line.strip().split()[0][5:] for line in text.splitlines()
            if line.strip().lower().startswith("mcp==")]
    return pins[0] if len(pins) == 1 else None


def _python_ready(python: Path, root: Path) -> bool:
    try:
        _run([str(python), "-c", "import pip"], root, timeout=30)
        return True
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        return False


def _prepare_python_cache(root: Path, offline: bool) -> None:
    """Resolve a changed pin before touching the working environment or tools."""
    cache = root / "tools/cache"
    lock, wheels = cache / "python-requirements.lock", cache / "wheels"
    if lock.is_file() and _locked_mcp(lock.read_text(encoding="utf-8")) == MCP_VERSION:
        return
    if offline:
        raise RuntimeError(f"Missing or stale Python lock for mcp=={MCP_VERSION}; run setup online once. Working tools and environment were preserved.")
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="python-download-", dir=cache) as temporary:
        staging = Path(temporary)
        staged_wheels = staging / "wheels"
        staged_wheels.mkdir()
        python = Path(sys.executable)
        if not _python_ready(python, root):
            _run([str(python), "-m", "venv", str(staging / "bootstrap")], root)
            python = staging / "bootstrap" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        _run([str(python), "-m", "pip", "download", "--only-binary", ":all:",
              "--index-url", "https://pypi.org/simple", "--dest", str(staged_wheels),
              f"mcp=={MCP_VERSION}"], root)
        text = _wheel_lock(staged_wheels)
        if _locked_mcp(text) != MCP_VERSION:
            raise RuntimeError("Downloaded wheel metadata does not match the requested MCP pin.")
        staged_lock = staging / "python-requirements.lock"
        staged_lock.write_text(text, encoding="utf-8")
        backups = cache / "backups"
        backups.mkdir(exist_ok=True)
        backup = Path(tempfile.mkdtemp(prefix="python-cache-", dir=backups))
        originals, installed = [], []
        try:
            for target in (wheels, lock):
                if target.exists():
                    os.replace(target, backup / target.name)
                    originals.append(target)
            for staged, target in ((staged_wheels, wheels), (staged_lock, lock)):
                os.replace(staged, target)
                installed.append(target)
        except BaseException:
            for target in reversed(installed):
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
            for target in reversed(originals):
                os.replace(backup / target.name, target)
            raise


def _cache_packages(root: Path) -> list[dict]:
    """Retain exact NuGet archives and upstream license declarations."""
    destination = root / "tools/cache/nuget"
    packages = []
    seen = set()
    for path in sorted((root / "tools/bin/.store").rglob("*.nupkg")):
        with zipfile.ZipFile(path) as archive:
            nuspecs = [name for name in archive.namelist() if name.endswith(".nuspec")]
            tree = ElementTree.fromstring(archive.read(nuspecs[0]))
            metadata = next(node for node in tree if node.tag.rsplit("}", 1)[-1] == "metadata")
            values = {node.tag.rsplit("}", 1)[-1]: node.text for node in metadata}
        package_id, version = values.get("id"), values.get("version")
        if (package_id, version) in seen:
            continue
        seen.add((package_id, version))
        filename = f"{package_id.lower()}.{version.lower()}.nupkg"
        cached = destination / filename
        if not cached.exists():
            shutil.copyfile(path, cached)
        if _hash(cached) != _hash(path):
            raise RuntimeError(f"Cached NuGet archive changed: {cached.name}")
        packages.append({"id": package_id, "version": version,
                         "source": f"https://api.nuget.org/v3-flatcontainer/{package_id.lower()}/{version.lower()}/{filename}",
                         "license": values.get("license") or values.get("licenseUrl"),
                         "path": str(cached.relative_to(root)), "sha256": _hash(cached)})
    return packages


def setup(root: Path = ROOT, offline: bool = False) -> dict:
    """Restore local tools, with explicit offline mode and no global installs."""
    root = Path(root).resolve()
    if not (root / "WORKSPACE_OWNERSHIP.md").is_file():
        raise ValueError("setup requires the owned forge root (WORKSPACE_OWNERSHIP.md).")
    dotnet = shutil.which("dotnet")
    if not dotnet:
        raise RuntimeError(".NET SDK is required. Install the official .NET 10 SDK, then run setup again.")
    sdk = _run([dotnet, "--version"], root)
    if int(sdk.split(".", 1)[0]) < 10:
        raise RuntimeError(f".NET 10 SDK required by ilspycmd; discovered {sdk}.")
    cache = root / "tools/cache"
    _prepare_python_cache(root, offline)
    for path in (root / "tools/bin", cache / "nuget"):
        path.mkdir(parents=True, exist_ok=True)
    # A private config prevents personal feeds/credentials from becoming build inputs.
    config = cache / "tool-sources.config"
    source = (cache / "nuget").as_uri() if offline else "https://api.nuget.org/v3/index.json"
    document = ElementTree.Element("configuration")
    sources = ElementTree.SubElement(document, "packageSources")
    ElementTree.SubElement(sources, "clear")
    ElementTree.SubElement(sources, "add", key="forge-tools", value=source)
    ElementTree.ElementTree(document).write(config, encoding="utf-8", xml_declaration=True)
    installed = _run([dotnet, "tool", "list", "--tool-path", str(root / "tools/bin")], root)
    for name, version in DOTNET_TOOLS.items():
        rows = [line.split() for line in installed.splitlines()]
        matches = [row for row in rows if len(row) > 1 and row[0].lower() == name]
        if matches and matches[0][1] != version:
            raise RuntimeError(f"Local {name} is {matches[0][1]}, expected {version}; preserve it and resolve this version conflict explicitly.")
        if not matches:
            _run([dotnet, "tool", "install", name, "--version", version,
                  "--tool-path", str(root / "tools/bin"), "--configfile", str(config)], root)
    paths = tool_paths(root)
    python = Path(paths["python"])
    # Preserve a healthy environment; repair an interrupted ensurepip only when needed.
    if not python.is_file() or not _python_ready(python, root):
        _run([sys.executable, "-m", "venv", str(root / ".venv")], root)
    lock = cache / "python-requirements.lock"
    _run([str(python), "-m", "pip", "install", "--no-index", "--require-hashes",
          "--find-links", str(cache / "wheels"), "-r", str(lock)], root)
    mcp = _run([str(python), "-c", "import importlib.metadata; print(importlib.metadata.version('mcp'))"], root)
    if mcp != MCP_VERSION:
        raise RuntimeError(f"MCP SDK is {mcp}, expected {MCP_VERSION}.")
    smoke = {}
    for name, version in DOTNET_TOOLS.items():
        # TCLI's CommandLineParser exits 1 for version/help; verify its exact text too.
        output = _run([paths[name], "--version"], root,
                      accepted_codes=(0, 1) if name == "tcli" else (0,))
        if not output.startswith(f"{name}{' ' if name == 'tcli' else ': '}{version}"):
            raise RuntimeError(f"Unexpected {name} version output: {output[:300]}")
        smoke[name] = output.splitlines()[:3]
    receipt = {
        "sdk": sdk, "python": sys.version.split()[0], "mcp": mcp,
        "tools": DOTNET_TOOLS, "paths": paths, "smoke": smoke,
        "nuget": _cache_packages(root),
        "wheels": [{"file": p.name, "sha256": _hash(p), "source": "https://pypi.org/simple"}
                   for p in sorted((cache / "wheels").glob("*.whl"))],
        "offline_note": "Caches are specific to this OS/architecture/Python version; runtimes are external prerequisites.",
    }
    (root / "tools/toolchain-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt
