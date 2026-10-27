"""Owned mod operations and read-only game inspection; no live deployment.

Requires Python 3.11+ and .NET for builds. JSON evidence lives beside builds;
optional diagnostic details go to stderr through the CLI's --debug switch.
"""
from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import struct
import subprocess
import tempfile
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
import zlib

from . import __version__

ROOT = Path(__file__).resolve().parents[1]
NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}\Z")
VERSION = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\Z")
DEPENDENCY = re.compile(r"[A-Za-z0-9_]+-[A-Za-z0-9_]+-[0-9]+\.[0-9]+\.[0-9]+\Z")
PINS = {"BepInEx.Core": "5.4.21", "RiskOfRain2.GameLibs": "1.5.0-r.1",
        "UnityEngine.Modules": "2021.3.45"}


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def safe_name(value: str) -> str:
    if not NAME.fullmatch(value) or value.upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
        raise ValueError("Use 1–64 letters/digits/underscores, starting with a letter; no device names.")
    return value


def owned(path: Path) -> Path:
    """Resolve links before writing so a junction cannot redirect output to a profile."""
    resolved = path.resolve()
    if not resolved.is_relative_to(ROOT.resolve()) or resolved == ROOT.resolve():
        raise ValueError(f"Output must remain inside the forge workspace: {path}")
    return resolved


def project(name: str) -> Path:
    return owned(ROOT / "projects" / safe_name(name))


def config() -> dict:
    path = ROOT / "forge.local.json"
    return read_json(path) if path.is_file() else {}


def discover() -> dict:
    """Use explicit overrides, then Steam library manifests and known manager roots."""
    settings = config()
    game_candidates = []
    override = os.environ.get("ROR2_GAME_DIR") or settings.get("game_dir")
    if override:
        game_candidates.append(Path(override))
    steam_roots = []
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
                steam_roots.append(Path(winreg.QueryValueEx(key, "SteamPath")[0]))
        except OSError:
            pass
    if os.environ.get("PROGRAMFILES(X86)"):
        steam_roots.append(Path(os.environ["PROGRAMFILES(X86)"]) / "Steam")
    steam_roots.extend([Path.home() / ".steam/steam", Path.home() / ".local/share/Steam"])
    for steam in list(steam_roots):
        libraries = steam / "steamapps/libraryfolders.vdf"
        if libraries.is_file():
            steam_roots.extend(Path(s.replace("\\\\", "\\")) for s in re.findall(r'"path"\s+"([^"\r\n]+)"', libraries.read_text(encoding="utf-8", errors="replace")))
    for steam in dict.fromkeys(steam_roots):
        game_candidates.append(steam / "steamapps/common/Risk of Rain 2")
    game = next((p.resolve() for p in game_candidates if (p / "Risk of Rain 2_Data/Managed/RoR2.dll").is_file()), None)
    if override and (game is None or game != Path(override).resolve()):
        raise ValueError("Configured ROR2_GAME_DIR/game_dir does not contain the RoR2 managed assembly.")
    manager_candidates = []
    manager_override = os.environ.get("ROR2_MODMAN_DIR") or settings.get("modman_dir")
    if manager_override:
        manager_candidates.append(Path(manager_override))
    appdata = Path(os.environ.get("APPDATA", Path.home() / ".config"))
    manager_candidates.extend([appdata / "r2modmanPlus-local/RiskOfRain2", appdata / "r2modman/RiskOfRain2", appdata / "Thunderstore Mod Manager/DataFolder/RiskOfRain2"])
    managers = list(dict.fromkeys(p.resolve() for p in manager_candidates if (p / "profiles").is_dir()))
    profiles = []
    for manager in managers:
        for profile in sorted((manager / "profiles").iterdir()):
            if profile.is_dir():
                manifests = []
                plugins = profile / "BepInEx/plugins"
                for manifest in sorted(plugins.glob("RiskofThunder-*/manifest.json")):
                    try:
                        metadata = read_json(manifest)
                        manifests.append({"name": metadata.get("name"), "version": metadata.get("version_number")})
                    except (OSError, ValueError):
                        continue
                profiles.append({"name": profile.name, "path": str(profile), "bepinex_core": (profile / "BepInEx/core/BepInEx.dll").is_file(),
                                 "log": str(profile / "BepInEx/LogOutput.log"), "package_manifests": manifests,
                                 "note": "Manifest presence is not proof a plugin is enabled or loaded."})
    result = {"game_dir": str(game) if game else None, "profiles": profiles}
    if game:
        managed = game / "Risk of Rain 2_Data/Managed/RoR2.dll"
        globals_file = game / "Risk of Rain 2_Data/globalgamemanagers"
        unity = re.search(rb"20[0-9]{2}\.[0-9]+\.[0-9]+[abfp][0-9]+", globals_file.read_bytes()[:1048576]) if globals_file.is_file() else None
        manifest = game.parent.parent / "appmanifest_632360.acf"
        build = re.search(r'"buildid"\s+"([0-9]+)"', manifest.read_text(encoding="utf-8")) if manifest.is_file() else None
        result.update({"steam_build": build.group(1) if build else None, "unity": unity.group().decode() if unity else None,
                       "assembly": str(managed), "assembly_sha256": sha256(managed), "runtime": "Unity Mono"})
    return result


def doctor() -> dict:
    from .toolchain import tool_paths
    tools = tool_paths()
    environment = discover()
    missing = [name for name, path in tools.items() if not Path(path).is_file()]
    sdk = shutil.which("dotnet")
    sdk_versions = []
    if sdk:
        probe = subprocess.run([sdk, "--list-sdks"], capture_output=True, text=True, timeout=15)
        if probe.returncode == 0:
            sdk_versions = [line.split()[0] for line in probe.stdout.splitlines() if line.strip()]
    return {"forge": __version__, "python": os.sys.version.split()[0], "python_executable": os.sys.executable,
            "dotnet": sdk, "sdks": sdk_versions, "tools": tools, "missing_tools": missing, **environment,
            "ready_for_build": bool(sdk_versions) and bool(environment.get("game_dir")),
            "ready_for_inspection": "ilspycmd" not in missing and bool(environment.get("game_dir")),
            "runtime_verified": False, "setup_command": "forge setup" if missing else None}


def make_icon() -> bytes:
    """A simple original forge marker; replace this placeholder before publication."""
    rows = []
    for y in range(256):
        row = bytearray([0])
        for x in range(256):
            bolt = (55 < y < 135 and 100 < x + (y - 55) // 2 < 180) or (125 < y < 205 and 120 < x + (y - 125) // 2 < 180)
            row.extend((255, 205, 74, 255) if bolt else (37, 46, 61, 255))
        rows.append(row)
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 256, 256, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b"")


def new_mod(name: str, author: str, template: str = "plugin", description: str = "A Risk of Rain 2 mod.") -> dict:
    safe_name(name)
    safe_name(author)
    if template not in {"plugin", "stats"}:
        raise ValueError("Unknown template; use plugin or stats.")
    if not description or len(description) > 250:
        raise ValueError("Description must contain 1–250 characters.")
    destination = project(name)
    if destination.exists():
        raise ValueError("Project already exists; existing source is never overwritten.")
    owned(destination.parent).mkdir(parents=True, exist_ok=True)
    # Complete the skeleton before exposing it as a usable project.
    staging = Path(tempfile.mkdtemp(prefix=".new-", dir=destination.parent))
    try:
        (staging / "src").mkdir()
        (staging / "content").mkdir()
        guid = f"{author.lower()}.{name.lower()}"
        refs = dict(PINS)
        dependencies = ["bbepis-BepInExPack-5.4.2122", "RiskofThunder-RoR2BepInExPack-1.49.0"]
        if template == "stats":
            refs["R2API.RecalculateStats"] = "1.7.0"
            dependencies.extend(["RiskofThunder-R2API_RecalculateStats-1.7.0", "RiskofThunder-HookGenPatcher-1.2.9"])
        references = "\n".join(f'    <PackageReference Include="{package}" Version="[{version}]" PrivateAssets="all" />' for package, version in refs.items())
        csproj = f'''<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>netstandard2.1</TargetFramework>
    <LangVersion>12.0</LangVersion>
    <Version>1.0.0</Version>
    <AssemblyName>{name}</AssemblyName>
    <RootNamespace>{name}</RootNamespace>
    <Deterministic>true</Deterministic>
    <RestorePackagesWithLockFile>true</RestorePackagesWithLockFile>
    <CopyLocalLockFileAssemblies>false</CopyLocalLockFileAssemblies>
  </PropertyGroup>
  <ItemGroup>
{references}
  </ItemGroup>
</Project>
'''
        (staging / "src" / f"{name}.csproj").write_text(csproj, encoding="utf-8")
        source = (ROOT / "templates" / f"{template}.cs").read_text(encoding="utf-8")
        for key, value in {"__NAME__": name, "__GUID__": guid}.items():
            source = source.replace(key, value)
        (staging / "src/Plugin.cs").write_text(source, encoding="utf-8")
        write_json(staging / "manifest.json", {"name": name, "version_number": "1.0.0", "website_url": "", "description": description, "dependencies": dependencies})
        write_json(staging / "forge.json", {"schema": 1, "name": name, "author": author, "guid": guid, "template": template, "version": "1.0.0", "runtime_verified": False})
        (staging / "README.md").write_text(f"# {name}\n\n{description}\n\nGenerated by RoR2 Forge. Runtime and multiplayer testing is pending.\n\n" + ("Movement speed multiplier is configurable; default 1.0 preserves normal speed. Install on host and clients for testing.\n" if template == "stats" else "Minimal BepInEx plugin with a configurable diagnostic log.\n") + "\nReplace the placeholder icon and document tested game builds before publishing.\n", encoding="utf-8")
        (staging / "icon.png").write_bytes(make_icon())
        (staging / "STATE.md").write_text("# Mod state\n\nVersion: 1.0.0\nSource: src/\nGoal: edit this mod, build, inspect, package, then test in a separate profile.\nDone: scaffold only.\nNext: build and runtime test.\nRuntime: unverified.\n", encoding="utf-8")
        (staging / "CHANGELOG.md").write_text("# 1.0.0\n\nInitial local source; runtime test pending.\n", encoding="utf-8")
        staging.rename(destination)
    except BaseException:
        shutil.rmtree(staging)
        raise
    return {"project": str(destination), "template": template, "next": f"forge build {name}", "runtime_verified": False}


def project_files(name: str) -> tuple[Path, Path, dict]:
    folder = project(name)
    metadata = read_json(folder / "forge.json")
    if metadata.get("name") != name or metadata.get("schema") != 1:
        raise ValueError("Project metadata does not match its owned folder/schema.")
    csproj = owned(folder / "src" / f"{name}.csproj")
    if not csproj.is_file():
        raise ValueError("Project source file is missing.")
    return folder, csproj, metadata


def source_digest(folder: Path) -> str:
    digest = hashlib.sha256()
    excluded = {"README.md", "STATE.md", "CHANGELOG.md", "icon.png", "manifest.json", "forge.json"}
    paths = [p for p in folder.rglob("*") if p.is_file() and p.name not in excluded and not {"build", "bin", "obj", ".git"}.intersection(p.relative_to(folder).parts)]
    for parent in (folder, *folder.parents):
        paths.extend(parent / name for name in ("Directory.Build.props", "Directory.Build.targets", "Directory.Packages.props", "NuGet.Config", "global.json") if (parent / name).is_file())
    for path in paths:
        if path.is_relative_to(folder):
            owned(path)
    for path in sorted(set(paths)):
        digest.update(str(path).replace("\\", "/").encode())
        digest.update(bytes.fromhex(sha256(path)))
    return digest.hexdigest()


def run_process(command: list[str], *, cwd: Path, env: dict | None = None, timeout: int = 300) -> subprocess.CompletedProcess:
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, shell=False)
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {command[0]}\n{(result.stdout + result.stderr)[-10000:]}")
    return result


def build(name: str, locked: bool = False, offline: bool = False) -> dict:
    from .toolchain import dotnet_env
    folder, csproj, metadata = project_files(name)
    output = owned(folder / "build/bin")
    output.mkdir(parents=True, exist_ok=True)
    # Refuse linked output/source trees before MSBuild executes a project.
    for path in folder.rglob("*"):
        owned(path)
    environment = dotnet_env()
    command = ["dotnet", "restore", str(csproj), "--configfile", str(ROOT / "NuGet.Config"), "--use-lock-file"]
    if locked:
        command.append("--locked-mode")
    if offline:
        command.extend(["--source", environment["NUGET_PACKAGES"], "-p:NuGetAudit=false"])
    log = owned(folder / "build/build.log")
    logs = ""
    try:
        logs = run_process(command, cwd=folder, env=environment).stdout
        logs += run_process(["dotnet", "build", str(csproj), "--no-restore", "--configuration", "Release", "--output", str(output)], cwd=folder, env=environment).stdout
    except Exception as exc:
        log.write_text(logs + str(exc), encoding="utf-8")
        raise
    log.write_text(logs, encoding="utf-8")
    dll = owned(output / f"{name}.dll")
    receipt = {"project": name, "version": metadata["version"], "assembly": str(dll), "assembly_sha256": sha256(dll), "source_sha256": source_digest(folder),
               "sdk": run_process(["dotnet", "--version"], cwd=folder, env=environment).stdout.strip(), "built_at": datetime.now(timezone.utc).isoformat(),
               "log": str(log), "warnings": sorted({line.strip() for line in logs.splitlines() if re.search(r"\bwarning [A-Z]+[0-9]+:", line)}), "runtime_verified": False}
    write_json(owned(folder / "build/receipt.json"), receipt)
    return receipt


def inspect(type_name: str, assembly: str | None = None, member: str | None = None) -> dict:
    from .toolchain import tool_command
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.+`]*", type_name):
        raise ValueError("Supply an exact .NET type name, e.g. RoR2.CharacterBody.")
    selected = Path(assembly).resolve() if assembly else Path(discover().get("assembly") or "")
    if not selected.is_file() or selected.suffix.lower() != ".dll":
        raise ValueError("A readable managed DLL is required; run doctor or pass --assembly.")
    if member and (len(member) > 1000 or not re.fullmatch(r"[A-Za-z0-9_:.,+`{}()\[\]#@*]+", member)):
        raise ValueError("Use an ILSpy XML documentation member ID or metadata token.")
    selector = ["--member", member] if member else ["--type", type_name]
    command = tool_command("ilspycmd") + ["--disable-updatecheck", *selector, "--referencepath", str(selected.parent), str(selected)]
    result = run_process(command, cwd=ROOT, timeout=180)
    if not result.stdout.strip():
        raise ValueError("ILSpy returned no type source.")
    return {"assembly": str(selected), "assembly_sha256": sha256(selected), "type": type_name, "member": member, "source": result.stdout, "redistribute": False}


def check_manifest(metadata: dict) -> list[str]:
    errors = []
    if not isinstance(metadata, dict):
        return ["manifest.json must be an object"]
    if not isinstance(metadata.get("name"), str) or not re.fullmatch(r"[A-Za-z0-9_]{1,128}", metadata["name"]):
        errors.append("invalid package name")
    if not isinstance(metadata.get("version_number"), str) or not VERSION.fullmatch(metadata["version_number"]):
        errors.append("version must be three numeric components")
    if not isinstance(metadata.get("description"), str) or len(metadata["description"]) > 250:
        errors.append("description must be a string of at most 250 characters")
    url = metadata.get("website_url")
    if not isinstance(url, str) or (url and not re.fullmatch(r"https?://[^\s/]+(?:/[^\s]*)?", url)):
        errors.append("website_url must exist and be empty or an HTTP(S) URL")
    deps = metadata.get("dependencies")
    if not isinstance(deps, list) or any(not isinstance(dep, str) or not DEPENDENCY.fullmatch(dep) for dep in deps):
        errors.append("dependencies must be Team-Package-Version strings")
    return errors


def check_icon(icon: bytes) -> bool:
    """Check complete PNG chunks/CRC and a bounded compressed image stream."""
    if icon[:8] != b"\x89PNG\r\n\x1a\n":
        return False
    offset, chunks, compressed, header = 8, [], bytearray(), None
    try:
        while offset < len(icon):
            length = struct.unpack(">I", icon[offset:offset + 4])[0]
            kind = icon[offset + 4:offset + 8]
            data = icon[offset + 8:offset + 8 + length]
            crc = struct.unpack(">I", icon[offset + 8 + length:offset + 12 + length])[0]
            if len(data) != length or zlib.crc32(kind + data) & 0xffffffff != crc:
                return False
            if kind == b"IDAT":
                compressed.extend(data)
            if kind == b"IHDR":
                if length != 13:
                    return False
                header = struct.unpack(">IIBBBBB", data)
                if header[:2] != (256, 256):
                    return False
            if kind == b"IEND" and length != 0:
                return False
            chunks.append(kind)
            offset += length + 12
        inflater = zlib.decompressobj()
        raw = inflater.decompress(compressed, 2 * 1024 * 1024)
        if not header or not inflater.eof or inflater.unused_data or chunks[0] != b"IHDR" or chunks[-1] != b"IEND" or chunks.count(b"IHDR") != 1:
            return False
        _, _, depth, color, compression, filtering, interlaced = header
        channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
        allowed_depths = {0: {1, 2, 4, 8, 16}, 2: {8, 16}, 3: {1, 2, 4, 8}, 4: {8, 16}, 6: {8, 16}}
        if color not in channels or depth not in allowed_depths[color] or compression or filtering or interlaced not in {0, 1} or (color == 3 and b"PLTE" not in chunks):
            return False
        # Adam7 pass sizes let us validate filter bytes without an image dependency.
        passes = [(0, 0, 1, 1)] if not interlaced else [(0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4), (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2)]
        position = 0
        for x, y, dx, dy in passes:
            width, height = (256 - x + dx - 1) // dx, (256 - y + dy - 1) // dy
            row_bytes = (width * channels[color] * depth + 7) // 8 + 1
            for _ in range(height):
                if position >= len(raw) or raw[position] > 4:
                    return False
                position += row_bytes
        return position == len(raw)
    except (struct.error, zlib.error, IndexError):
        return False


def validate(archive: str | Path) -> dict:
    path = Path(archive).resolve()
    errors = []
    with zipfile.ZipFile(path) as package:
        entries = package.infolist()
        names = [entry.filename for entry in entries]
        if len({name.casefold() for name in names}) != len(names):
            errors.append("duplicate or case-colliding archive paths")
        total = sum(entry.file_size for entry in entries)
        if total > 512 * 1024 * 1024 or len(entries) > 10000:
            raise ValueError("Archive exceeds the validator's 512 MiB/10000 entry inspection limit.")
        for entry in entries:
            parts = entry.filename.rstrip("/").split("/")
            if not parts or entry.filename.startswith("/") or "\\" in entry.filename or any(part in {"..", ".", ""} or ":" in part for part in parts):
                errors.append(f"unsafe archive path: {entry.filename}")
            if (entry.external_attr >> 16) & 0o170000 == 0o120000:
                errors.append(f"archive symlink: {entry.filename}")
            if PurePosixPath(entry.filename).name.casefold() in {"ror2.dll", "assembly-csharp.dll", "bepinex.dll", "unityengine.dll", "0harmony.dll"} or PurePosixPath(entry.filename).name.casefold().startswith("unityengine."):
                errors.append(f"third-party runtime/game assembly must not be shipped: {entry.filename}")
        required = {"manifest.json", "README.md", "icon.png"}
        if not required.issubset(names):
            errors.append("ZIP root requires manifest.json, README.md and icon.png")
        else:
            if any(package.getinfo(name).file_size > 8 * 1024 * 1024 for name in required):
                raise ValueError("Package metadata exceeds the 8 MiB per-file inspection limit.")
            try:
                errors.extend(check_manifest(json.loads(package.read("manifest.json").decode("utf-8-sig"))))
                if not package.read("README.md").decode("utf-8-sig").strip():
                    errors.append("README.md must not be empty")
            except (ValueError, UnicodeError) as exc:
                errors.append(f"invalid UTF-8/JSON metadata: {exc}")
            icon = package.read("icon.png")
            if not check_icon(icon):
                errors.append("icon.png must be a 256×256 PNG")
        if package.testzip():
            errors.append("archive CRC check failed")
    return {"valid": not errors, "archive": str(path), "sha256": sha256(path), "files": names, "errors": errors, "runtime_verified": False}


def package_mod(name: str) -> dict:
    folder, csproj, metadata = project_files(name)
    safe_name(metadata["author"])
    if not VERSION.fullmatch(metadata["version"]):
        raise ValueError("Invalid mod version in forge.json.")
    receipt = read_json(folder / "build/receipt.json")
    dll = owned(folder / "build/bin" / f"{name}.dll")
    manifest = read_json(folder / "manifest.json")
    errors = check_manifest(manifest)
    if errors:
        raise ValueError("; ".join(errors))
    if manifest["name"] != name or manifest["version_number"] != metadata["version"] or ET.parse(csproj).findtext(".//Version") != metadata["version"]:
        raise ValueError("Manifest, forge.json and csproj name/version must agree.")
    plugin_source = (folder / "src/Plugin.cs").read_text(encoding="utf-8")
    if f'PluginVersion = "{metadata["version"]}"' not in plugin_source:
        raise ValueError("PluginVersion must agree with the package version.")
    if receipt.get("source_sha256") != source_digest(folder) or receipt.get("assembly_sha256") != sha256(dll):
        raise ValueError("Source or DLL changed since the successful build; build again before packaging.")
    output = owned(ROOT / "artifacts" / f"{metadata['author']}-{name}-{metadata['version']}.zip")
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {"manifest.json": folder / "manifest.json", "README.md": folder / "README.md", "icon.png": folder / "icon.png", f"plugins/{name}/{name}.dll": dll}
    content = folder / "content"
    for item in sorted(content.rglob("*")) if content.exists() else []:
        owned(item)
        if item.is_file():
            if item.suffix.lower() in {".dll", ".exe", ".pdb", ".cs", ".csproj", ".py", ".ps1", ".cmd", ".bat", ".nupkg", ".zip", ".7z"}:
                raise ValueError(f"content/ is for runtime assets, not code or archives: {item.name}")
            payload[f"plugins/{name}/{item.relative_to(content).as_posix()}"] = item
    for license_name in ("LICENSE", "LICENSE.txt", "LICENSE.md"):
        if (folder / license_name).is_file():
            payload[license_name] = folder / license_name
    if len({path.casefold() for path in payload}) != len(payload):
        raise ValueError("Package paths collide; rename content files.")
    for item in payload.values():
        owned(item)
    with tempfile.NamedTemporaryFile(dir=output.parent, suffix=".zip", delete=False) as stream:
        staging = Path(stream.name)
    try:
        with zipfile.ZipFile(staging, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as package:
            for archive_name, source in sorted(payload.items()):
                entry = zipfile.ZipInfo(archive_name, date_time=(2020, 1, 1, 0, 0, 0))
                entry.compress_type = zipfile.ZIP_DEFLATED
                entry.external_attr = 0o100644 << 16
                package.writestr(entry, source.read_bytes())
        result = validate(staging)
        if not result["valid"]:
            raise ValueError("; ".join(result["errors"]))
        if output.exists() and sha256(output) != result["sha256"]:
            raise ValueError("Different package bytes already exist for this version; bump the mod version.")
        os.replace(staging, output)
    finally:
        staging.unlink(missing_ok=True)
    return {**result, "archive": str(output), "build_receipt": str(folder / "build/receipt.json"), "publish": "not requested"}


def logs(path: str | None = None, lines: int = 250) -> dict:
    if not 1 <= lines <= 5000:
        raise ValueError("Read 1–5000 trailing lines.")
    selected = Path(path).resolve() if path else None
    if selected is None:
        candidates = [Path(profile["log"]) for profile in discover()["profiles"] if Path(profile["log"]).is_file()]
        if not candidates:
            raise ValueError("No BepInEx log exists yet; launch a test profile or pass --path.")
        selected = max(candidates, key=lambda item: (item.stat().st_mtime_ns, str(item)))
    with selected.open(encoding="utf-8-sig", errors="replace") as stream:
        tail = list(deque(stream, maxlen=lines))
    issues = [line.rstrip() for line in tail if re.search(r"error|exception|could not load|missingmethod|typeload|failed", line, re.I)]
    return {"path": str(selected), "tail": "".join(tail), "possible_issues": issues,
            "note": "Text matches are triage candidates, not a crash diagnosis or runtime success proof."}


def lookup(namespace: str, name: str, version: str | None = None) -> dict:
    for token in (namespace, name):
        safe_name(token)
    if version and not VERSION.fullmatch(version):
        raise ValueError("Version must be three numeric components.")
    url = f"https://thunderstore.io/api/experimental/package/{namespace}/{name}/" + (f"{version}/" if version else "")
    request = urllib.request.Request(url, headers={"User-Agent": f"RoR2Forge/{__version__}", "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = response.read(4 * 1024 * 1024 + 1)
    if len(payload) > 4 * 1024 * 1024:
        raise ValueError("Unexpectedly large package response.")
    return {"url": url, "metadata": json.loads(payload), "read_only": True}


def guide(topic: str = "overview") -> dict:
    mapping = {"overview": "AGENT_GUIDE.md", "code": "RECIPES.md", "content": "RECIPES.md", "assets": "RECIPES.md", "networking": "RECIPES.md", "debugging": "RECIPES.md"}
    if topic not in mapping:
        raise ValueError(f"Unknown guide topic: {topic}")
    path = ROOT / "docs" / mapping[topic]
    return {"topic": topic, "path": str(path), "text": path.read_text(encoding="utf-8")}
