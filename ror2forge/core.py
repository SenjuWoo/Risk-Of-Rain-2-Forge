"""Owned mod operations and read-only game inspection; no live deployment.

Requires Python 3.11+ and .NET for builds. JSON evidence lives beside builds;
optional diagnostic details go to stderr through the CLI's --debug switch.
"""
from __future__ import annotations

from collections import deque
from .safefs import Budget, read_bounded
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


def _reparse_point(path: Path) -> bool:
    """True for a symlink or a Windows reparse point (junction), without following it."""
    try:
        info = path.lstat()
    except OSError:
        return False
    return path.is_symlink() or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def project_input(folder: Path, path: Path) -> Path:
    """Validate an input file against one project's own boundary.

    `owned()` only promises the forge workspace, which is too wide: a link from projects/A into projects/B
    still lands inside the workspace while handing another mod's bytes to the packer. Every input is checked
    for reparse points from the file up to its project root, then resolved and re-checked against that root.
    """
    folder = folder.resolve()
    candidate = path.absolute()
    for ancestor in (candidate, *candidate.parents):
        if ancestor == folder.parent:
            break
        if _reparse_point(ancestor):
            raise ValueError(f"Project inputs may not be links or junctions: {ancestor}")
    resolved = candidate.resolve()
    if resolved != folder and folder not in resolved.parents:
        raise ValueError(f"Input escapes its project: {path}")
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



def wwise_status() -> dict:
    """Locate Wwise authoring installs. Custom sound banks cannot be built without one."""
    roots = [Path(r"C:\Program Files (x86)\Audiokinetic"), Path(r"C:\Program Files\Audiokinetic")]
    installs = []
    for root in roots:
        if not root.is_dir():
            continue
        for directory in sorted(root.glob("Wwise *")):
            console = directory / "Authoring" / "x64" / "Release" / "bin" / "WwiseConsole.exe"
            installs.append({"path": str(directory), "version": directory.name.replace("Wwise ", ""),
                             "console": str(console) if console.is_file() else None})
    matching = [i for i in installs if i["version"].startswith("2023.1") and i["console"]]
    return {"required": "2023.1", "installs": installs, "ready": bool(matching),
            "note": None if matching else "No Wwise 2023.1 authoring install found; custom sound banks need it (account-gated download). See docs/AUDIO.md."}


def doctor() -> dict:
    from .toolchain import dotnet_env, tool_paths
    tools = tool_paths()
    environment = discover()
    missing = [name for name, path in tools.items() if not Path(path).is_file()]
    sdk = shutil.which("dotnet")
    sdk_versions = []
    selected_sdk, sdk_error = None, None
    if sdk:
        probe = subprocess.run([sdk, "--list-sdks"], capture_output=True, text=True, cwd=ROOT, env=dotnet_env(), timeout=15)
        if probe.returncode == 0:
            sdk_versions = [line.split()[0] for line in probe.stdout.splitlines() if line.strip()]
        selected = subprocess.run([sdk, "--version"], capture_output=True, text=True, cwd=ROOT, env=dotnet_env(), timeout=15)
        if selected.returncode == 0 and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[\w.-]+)?", selected.stdout.strip()):
            selected_sdk = selected.stdout.strip()
        else:
            sdk_error = (selected.stderr or selected.stdout).strip()[:1000] or "The .NET SDK could not be resolved from the forge root."
    return {"forge": __version__, "python": os.sys.version.split()[0], "python_executable": os.sys.executable,
            "dotnet": sdk, "sdks": sdk_versions, "selected_sdk": selected_sdk, "sdk_error": sdk_error, "tools": tools, "missing_tools": missing, **environment,
            "ready_for_build": selected_sdk is not None and int(selected_sdk.split(".")[0]) >= 8,
            "ready_for_inspection": "ilspycmd" not in missing and bool(environment.get("game_dir")),
            "wwise": wwise_status(),
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
    if template not in {"plugin", "stats", "procedural"}:
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
        (staging / "README.md").write_text(f"# {name}\n\n{description}\n\nGenerated by RoR2 Forge. Runtime and multiplayer testing is pending.\n\n" + ("Movement speed multiplier is configurable; default 1.0 preserves normal speed. Install on host and clients for testing.\n" if template == "stats"
                else "Builds geometry at runtime with no Unity editor, no AssetBundle and no paid tool: a noise-displaced icosphere with radius, subdivision and roughness in the config. Use it for placeholder or shipped shapes.\n" if template == "procedural"
                else "Minimal BepInEx plugin with a configurable diagnostic log.\n") + "\nReplace the placeholder icon and document tested game builds before publishing.\n", encoding="utf-8")
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


# Root documentation is excluded by location. packages.lock.json is excluded because `dotnet restore`
# writes it during the build; its content is still reported in the receipt via the SDK/lock info.
ROOT_DOC_FILES = {"README.md", "STATE.md", "CHANGELOG.md", "icon.png", "manifest.json", "forge.json",
                  "packages.lock.json"}


def source_digest(folder: Path) -> str:
    """Digest of what the compiler reads: sources and build props, not docs or packaged assets.

    Root documentation is excluded by *location*; a same-named file under content/ is a runtime
    asset and must change the digest when it changes.
    """
    digest = hashlib.sha256()
    paths = [p for p in folder.rglob("*") if p.is_file()
             and p.name != "packages.lock.json"      # written by `dotnet restore`, not authored here
             and not (p.parent == folder and p.name in ROOT_DOC_FILES)
             and "content" not in p.relative_to(folder).parts
             and not {"build", "bin", "obj", ".git"}.intersection(p.relative_to(folder).parts)]
    for parent in (folder, *folder.parents):
        paths.extend(parent / name for name in ("Directory.Build.props", "Directory.Build.targets", "Directory.Packages.props", "NuGet.Config", "global.json") if (parent / name).is_file())
    for path in paths:
        if path.is_relative_to(folder):
            owned(path)
    for path in sorted(set(paths)):
        digest.update(str(path).replace("\\", "/").encode())
        digest.update(bytes.fromhex(sha256(path)))
    return digest.hexdigest()


def package_digest(folder: Path) -> str:
    """Digest of the packaged inputs (metadata, icon, README, content, licences).

    Kept separate from source_digest so a content or manifest change invalidates packaging
    provenance without pretending the compiled assembly changed.
    """
    digest = hashlib.sha256()
    names = {"manifest.json", "README.md", "icon.png", "LICENSE", "LICENSE.txt", "LICENSE.md"}
    paths = [p for p in folder.rglob("*")
             if p.is_file()
             and not {"build", "bin", "obj", ".git"}.intersection(p.relative_to(folder).parts)
             and (p.parent == folder and p.name in names or "content" in p.relative_to(folder).parts)]
    for path in sorted(set(paths)):
        digest.update(str(path.relative_to(folder)).replace("\\", "/").encode())
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
    before = (source_digest(folder), package_digest(folder))
    log = owned(folder / "build/build.log")
    logs = ""
    try:
        logs = run_process(command, cwd=folder, env=environment).stdout
        logs += run_process(["dotnet", "build", str(csproj), "--no-restore", "--configuration", "Release", "--output", str(output)], cwd=folder, env=environment).stdout
    except Exception as exc:
        log.write_text(logs + str(exc), encoding="utf-8")
        raise
    log.write_text(logs, encoding="utf-8")
    after = (source_digest(folder), package_digest(folder))
    if after != before:
        raise RuntimeError("Project inputs changed while the build ran; no trustworthy receipt was written. Build again.")
    dll = owned(output / f"{name}.dll")
    lock = next((candidate for candidate in (folder / "src/packages.lock.json", folder / "packages.lock.json")
                 if candidate.is_file()), None)
    if locked and lock is None:
        raise RuntimeError("--locked needs an existing packages.lock.json; run a normal build first.")
    receipt = {"project": name, "lock_sha256": sha256(lock) if lock else None, "version": metadata["version"], "assembly": str(dll), "assembly_sha256": sha256(dll), "source_sha256": after[0], "package_sha256": after[1],
               "sdk": run_process(["dotnet", "--version"], cwd=folder, env=environment).stdout.strip(), "built_at": datetime.now(timezone.utc).isoformat(),
               "log": str(log), "warnings": sorted({line.strip() for line in logs.splitlines() if re.search(r"\bwarning [A-Z]+[0-9]+:", line)}), "runtime_verified": False}
    write_json(owned(folder / "build/receipt.json"), receipt)
    return receipt


def assembly_path(assembly: str | None = None) -> Path:
    selected = Path(assembly).resolve() if assembly else Path(discover().get("assembly") or "")
    if not selected.is_file() or selected.suffix.lower() != ".dll":
        raise ValueError("A readable managed DLL is required; run doctor or pass --assembly.")
    return selected


def symbols(query: str, assembly: str | None = None, limit: int = 20) -> dict:
    """Search ILSpy's type inventory rather than decompiling an assembly into context."""
    from .toolchain import tool_command
    if not query.strip() or len(query) > 256 or any(ord(char) < 32 for char in query):
        raise ValueError("Supply a nonempty type search of at most 256 characters without control characters.")
    if not 1 <= limit <= 200:
        raise ValueError("Return 1–200 symbols.")
    selected = assembly_path(assembly)
    result = run_process(tool_command("ilspycmd") + ["--disable-updatecheck", "--list", "cisde", str(selected)], cwd=ROOT, timeout=180)
    matches = []
    for line in result.stdout.splitlines():
        kind, separator, name = line.partition(" ")
        # Compiler-generated helper names are not useful entry points for mod authors.
        if separator and "<" not in name and query.casefold() in name.casefold():
            matches.append({"kind": kind.lower(), "name": name})
    matches.sort(key=lambda item: (item["name"].casefold() != query.casefold(), item["name"].casefold(), item["kind"]))
    return {"assembly": str(selected), "assembly_sha256": sha256(selected), "query": query,
            "total": len(matches), "truncated": len(matches) > limit, "symbols": matches[:limit], "redistribute": False}


def inspect(type_name: str, assembly: str | None = None, member: str | None = None) -> dict:
    from .toolchain import tool_command
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.+`]*", type_name):
        raise ValueError("Supply an exact .NET type name, e.g. RoR2.CharacterBody.")
    selected = assembly_path(assembly)
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



# Thunderstore's installer keeps only these top-level routes (optionally under BepInEx/) and empties
# every other folder into the package root. A mod that ships assets/ beside its DLL therefore installs
# as loose files and dies on a missing path - a failure that looks fine in the ZIP and in manual
# extraction, which is exactly how it reaches users.
INSTALL_ROUTES = {"plugins", "patchers", "config", "core", "monomod"}


def layout_problems(names: list[str]) -> list[str]:
    """Folders the installer will empty, and therefore paths the installed mod can no longer open."""
    lost: dict[str, int] = {}
    for name in names:
        parts = name.rstrip("/").split("/")
        if len(parts) < 2:
            continue
        head = parts[0].casefold()
        if head == "bepinex" and len(parts) > 2 and parts[1].casefold() in INSTALL_ROUTES:
            continue
        if head in INSTALL_ROUTES:
            continue
        lost[parts[0]] = lost.get(parts[0], 0) + 1
    return [f"top-level folder '{folder}/' ({count} files) is not an install route; the manager empties it "
            f"into the package root, so any code opening '{folder}/...' fails after install. Move it under plugins/."
            for folder, count in sorted(lost.items())]


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
        errors.extend(layout_problems(names))
        if package.testzip():
            errors.append("archive CRC check failed")
    return {"valid": not errors, "archive": str(path), "sha256": sha256(path), "files": names, "errors": errors, "runtime_verified": False}



# ---------------------------------------------------------------- project audit
# R2API split into per-module assemblies at 5.0. A module used in code but missing from the manifest is the
# most common "works on my machine, fails for users" bug: the plugin simply never loads. These checks compare
# what the C# actually references against what the package declares.

R2API_GUID_PREFIX = "com.bepis.r2api."
# Namespaces that ship inside R2API.Core.dll rather than a split module of the same name (read from
# R2API_Core 5.3.0); `using R2API.Utils;` for NetworkCompatibility needs R2API_Core, not an "R2API_Utils".
R2API_CORE_NAMESPACES = {"Utils": "Core", "MiscHelpers": "Core", "AutoVersionGen": "Core"}
# A qualified `R2API.X.Y` names a *type* in the root namespace, not a module. Only types we can map with
# confidence count as a dependency; anything else is ignored rather than guessed into a false error.
# Ownership is data, not a guess: ror2forge/r2api_ownership.json records where every module and API class
# came from (upstream repo, ref, date). Regenerate it with scripts/refresh_r2api_ownership.py.
_OWNERSHIP = json.loads((Path(__file__).with_name("r2api_ownership.json")).read_text(encoding="utf-8"))
R2API_MODULES = set(_OWNERSHIP["modules"])
R2API_TYPE_MODULES: dict[str, str] = dict(_OWNERSHIP["types"])


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _source_files(root: Path) -> list[Path]:
    skip = {"bin", "obj", ".git", "node_modules", "dist", "build"}
    return [f for f in root.rglob("*.cs") if not skip & {part.lower() for part in f.parts}]


def _manifest_for(root: Path) -> tuple[Path | None, dict]:
    candidates = [p for p in root.rglob("manifest.json") if "bin" not in {x.lower() for x in p.parts} and "obj" not in {x.lower() for x in p.parts}]
    if not candidates:
        return None, {}
    path = sorted(candidates, key=lambda p: len(p.parts))[0]
    return path, json.loads(path.read_text(encoding="utf-8-sig"))


def _csharp_literal_end(text: str, i: int) -> int:
    """Return the index just past a C# literal starting at i, or i+1 when this is not a literal.

    Handles normal, verbatim (@), interpolated ($, $$) and raw (\"\"\") strings plus char literals.
    Interpolation holes are treated as part of the literal: this is a lexer for audit scans, not a parser,
    and a brace hole that contains its own quotes is reported as such rather than silently misread.
    """
    n = len(text)
    dollars, verbatim, j = 0, False, i
    while j < n and text[j] in "$@":
        if text[j] == "$":
            dollars += 1
        else:
            verbatim = True
        j += 1
    if j < n and text[j] == "'" and dollars == 0 and not verbatim:
        # char literal: '\'' or 'x'
        k = j + 1
        while k < n:
            if text[k] == "\\":
                k += 2
                continue
            if text[k] == "'" or text[k] == "\n":
                return k + 1
            k += 1
        return n
    if j >= n or text[j] != '"':
        return i + 1
    quotes = 0
    while j + quotes < n and text[j + quotes] == '"':
        quotes += 1
    if quotes >= 3:                      # raw string: ends at the same quote run
        closing = '"' * quotes
        end = text.find(closing, j + quotes)
        return n if end < 0 else end + quotes
    j += 1
    if verbatim and not dollars:
        while j < n:
            if text[j] == '"':
                if j + 1 < n and text[j + 1] == '"':
                    j += 2
                    continue
                return j + 1
            j += 1
        return n
    while j < n:
        if text[j] == "\\":
            j += 2
            continue
        if text[j] == '"':
            return j + 1
        if text[j] == "\n":
            return j
        j += 1
    return n


def _strip_csharp(text: str, keep_strings: bool = False) -> str:
    """Return text with comments blanked, and (unless keep_strings) literal contents blanked.

    One scanner serves every audit check: comments are recognised only in code, and a literal is scanned
    through its own rules, so `//` inside "https://..." never starts a comment. Newlines and offsets are
    preserved so messages still line up with the file.
    """
    out, i, n = [], 0, len(text)
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if ch == "/" and nxt == "/":
            end = text.find("\n", i)
            end = n if end < 0 else end
            out.append(" " * (end - i))
            i = end
        elif ch == "/" and nxt == "*":
            end = text.find("*/", i + 2)
            end = n if end < 0 else end + 2
            out.append("".join("\n" if c == "\n" else " " for c in text[i:end]))
            i = end
        elif ch == '"' or ch == "'" or ch in "$@":
            end = _csharp_literal_end(text, i)
            if end <= i:                 # defensive: never spin on a malformed literal
                out.append(ch)
                i += 1
                continue
            chunk = text[i:end]
            out.append(chunk if keep_strings else "".join("\n" if c == "\n" else " " for c in chunk))
            i = end
        else:
            out.append(ch)
            i += 1
    return "".join(out)



def audit_project(root: str | Path) -> dict:
    """Cross-check C# R2API usage and BepInDependency GUIDs against the package manifest."""
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError("audit needs a mod directory")
    sources = _source_files(root)
    manifest_path, manifest = _manifest_for(root)
    if not sources:
        raise ValueError("no C# sources found")
    if not manifest:
        raise ValueError("no manifest.json found")

    declared = set()
    for dep in manifest.get("dependencies", []):
        parts = dep.split("-")
        if len(parts) < 3:
            continue
        package = parts[1]
        if package.lower().startswith("r2api_"):
            package = package[len("r2api_"):]      # RiskofThunder-R2API_Skins vs GUID com.bepis.r2api.skins
        declared.add(_norm(package))
    declared_full = set(manifest.get("dependencies", []))

    guids, imports, unresolved = set(), set(), set()
    texts = {}
    for path in sources:
        raw = path.read_text(encoding="utf-8-sig", errors="replace")
        text = _strip_csharp(raw)
        texts[path] = text
        # Attributes carry the GUID inside a string literal, so keep literals for this one scan.
        guids.update(re.findall(r'\[BepInDependency\(\s*"([^"]+)"', _strip_csharp(raw, keep_strings=True)))
        # using R2API.X;  global using R2API.X;  using Alias = R2API.X.Y;  using static R2API.X.Y;
        imports.update(re.findall(
            r'^\s*(?:global\s+)?using\s+(?:static\s+)?(?:global\s*::\s*)?(?:[A-Za-z_][\w.]*\s*=\s*(?:global\s*::\s*)?)?R2API\.([A-Za-z0-9_]+)',
            text, re.M))
        # `using R2API;` followed by a bare `SkillsAPI.…` is the most common form in real mods, so known
        # API class names count wherever they appear in code.
        for known, module in R2API_TYPE_MODULES.items():
            if known == "R2API":        # the root static class doubles as the namespace prefix
                continue
            # A mod that declares its own class of that name is not referencing R2API.
            declares_own = re.search(rf"\b(?:class|struct|interface|enum|record)\s+{known}\b", text)
            if not declares_own and re.search(rf"(?<!\.)\b{known}\b", text):
                imports.add(module)
        # A qualified `R2API.X` is a namespace when X is a module, a type when X is a known API class;
        # anything else is recorded as unresolved instead of being guessed into a package name.
        for name in re.findall(r"\bR2API\.([A-Za-z0-9_]+)\s*\.", text):
            if name in R2API_MODULES:
                imports.add(name)
            elif name in R2API_TYPE_MODULES:
                imports.add(R2API_TYPE_MODULES[name])
            else:
                unresolved.add(name)

    errors, warnings = [], []
    _unresolved = sorted(unresolved)
    if _unresolved:
        # Unknown names are not assumed to be packages: report them and let a human decide.
        warnings.append("unresolved R2API references (not in ror2forge/r2api_ownership.json): "
                        + ", ".join(_unresolved) + " - verify the owning module before release")

    # 1. every R2API namespace used needs its own split module in the manifest
    for module in sorted(imports):
        owner = R2API_CORE_NAMESPACES.get(module, module)
        if _norm(owner) not in declared:
            errors.append(f"using R2API.{module}; but no RiskofThunder-R2API_{module} dependency in {manifest_path.name}")

    # 2. every BepInDependency GUID should correspond to a declared package
    for guid in sorted(guids):
        if guid.startswith(R2API_GUID_PREFIX):
            module = guid[len(R2API_GUID_PREFIX):]
            if _norm(module) not in declared:
                errors.append(f"[BepInDependency(\"{guid}\")] but no matching R2API_{module} dependency in {manifest_path.name}")
        # Non-R2API GUIDs (BepInEx, other mods) have no reliable GUID->package mapping; guessing produced
        # false positives, so they are left alone. The R2API split is the failure this check exists for.

    # 3. searchable attributes only work when the assembly opts in
    # Two views: literals blanked (identifier checks) and literals kept (attribute/event names). Comments are
    # gone from both, so a commented-out line can no longer trip a check.
    joined = "\n".join(texts[path] for path in sources)
    joined_strings = "\n".join(_strip_csharp(path.read_text(encoding="utf-8-sig", errors="replace"), keep_strings=True)
                               for path in sources)
    if "SearchableAttribute.OptIn" not in joined and re.search(r"\[RegisterAchievement|\[Searchable", joined):
        warnings.append("uses searchable/achievement attributes but no [assembly: HG.Reflection.SearchableAttribute.OptIn]")

    # 4. every audio event a source file plays must exist in the shipped event map, or it is silently silent
    # (a transform voice line pointed at a League event that was never extracted, and nothing errored)
    events_files = [p for p in (root / "content").rglob("events.txt")] if (root / "content").is_dir() else []
    stray_maps = [p for p in root.rglob("events.txt")
                  if p not in events_files and not {"bin", "obj", "build"} & {x.lower() for x in p.parts}]
    if stray_maps and not events_files:
        errors.append(f"{stray_maps[0].name} sits outside content/ and would not ship; move it under content/ "
                      "or delete it (docs/AUDIO.md)")
    if events_files:
        keys = set()
        for path in events_files:
            for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
                if "=" in line and not line.lstrip().startswith("#"):
                    key, _files = line.split("=", 1)
                    keys.add(key.strip())
                    for asset in (part.strip() for part in _files.split(",")):
                        if asset and not list((root / "content").rglob(asset)):
                            errors.append(f'event map lists "{asset}" for {key.strip()} but no such file is packaged')
        for ev in sorted(set(re.findall(r'"(Play_[A-Za-z0-9_]+)"', joined_strings)) - keys):
            errors.append(f'"{ev}" is played in C# but missing from {events_files[0].name}')

    # 5. the manifest, csproj and plugin attribute must carry one version (three places drift apart by hand)
    version = manifest.get("version_number")
    # build/ holds version backups and intermediate output; a stale copy there is not the project.
    for csproj in [p for p in root.rglob("*.csproj")
                   if not {"bin", "obj", "build"} & {x.lower() for x in p.parts}]:
        found = ET.parse(csproj).findtext(".//Version")
        if found and version and found != version:
            errors.append(f"{csproj.name} <Version> {found} != manifest version_number {version}")
    for literal in set(re.findall(r'\bconst\s+string\s+\w*Version\s*=\s*"(\d+\.\d+\.\d+)"', joined_strings)):
        if version and literal != version:
            errors.append(f'C# version constant "{literal}" != manifest version_number {version}')

    # 6-9. survivor polish that compiles, validates and plays, so nothing else catches it (Ultron 1.1.2/1.2.0 audit)
    # Evaluated per file: a correct pattern in one file must not excuse a wrong one in another.
    for text in texts.values():
        for warning in survivor_warnings(text):
            if warning not in warnings:
                warnings.append(warning)

    return {"root": str(root), "manifest": str(manifest_path), "sources": len(sources),
            "r2api_modules": sorted(imports),
        "r2api_unresolved": sorted(unresolved), "dependency_guids": sorted(guids),
            "dependencies_declared": len(declared_full), "errors": errors, "warnings": warnings,
            "valid": not errors}


_ATTACK = re.compile(r"\bnew\s+(?:BulletAttack|BlastAttack|OverlapAttack)\b")
_DAMAGE_TYPE = re.compile(r"\bdamageType\s*=\s*([^;,\n(]+(?:\([^)]*\))?)")


def survivor_warnings(source: str) -> list[str]:
    """Warnings for survivor gaps that play fine in a solo test; each one names the fix in docs/RUNTIME.md."""
    warnings = []
    if re.search(r"\bAddSurvivorDef\b|ScriptableObject\.CreateInstance<SurvivorDef>", source) and "itemDisplayRuleSet" not in source:
        warnings.append("registers a survivor but never sets CharacterModel.itemDisplayRuleSet, so picked-up items are "
                        "invisible on the model (docs/RUNTIME.md, 'Item displays')")
    if _ATTACK.search(source):
        untagged = sorted({m.group(1).strip().rstrip(",") for m in _DAMAGE_TYPE.finditer(source)
                           if "DamageType." in m.group(1) and "DamageSource" not in m.group(1)
                           and not re.search(r"Generic(Primary|Secondary|Utility|Special)", m.group(1))})
        if untagged:
            warnings.append("attack damageType without a DamageSource (" + "; ".join(untagged[:4]) + "): skill-keyed items "
                            "ignore these hits. Use new DamageTypeCombo(type, DamageTypeExtended.Generic, DamageSource.Primary|...) "
                            "(docs/RUNTIME.md, 'Damage source')")
    if "waveOutWrite" in source and not re.search(r"cvVolumeSfx|volume_sfx", source):
        warnings.append("plays through waveOut but never reads the game's SFX volume; the in-game slider does nothing "
                        "(docs/AUDIO.md, Route B)")
    # Compress() needs readable pixels; Apply(false, true) then frees the CPU copy, so that pair is the correct
    # pattern. Paired per receiver: an unrelated Apply on another texture must not excuse the leak.
    for match in re.finditer(r"(?:(\w+)\s*\.\s*)?LoadImage\s*\(([^;]*),\s*false\s*\)", source):
        # `tex.LoadImage(bytes, false)` and the static `ImageConversion.LoadImage(tex, bytes, false)`
        receiver, arguments = match.group(1), match.group(2)
        texture = receiver if receiver and receiver != "ImageConversion" else arguments.split(",")[0].strip()
        if not texture or not re.search(rf"\b{re.escape(texture)}\s*\.\s*Apply\s*\([^;)]*,\s*true\s*\)", source):
            warnings.append("ImageConversion.LoadImage(..., false) keeps a CPU copy of every texture; pass true unless "
                            "the pixels are read back (docs/RUNTIME.md, 'Texture memory')")
            break
    return warnings


def plugin_version_declaration(source: str) -> re.Match:
    """Find the generated literal declaration without treating comments as code."""
    # shortcut: raw C# strings need a syntax-aware editor; refuse them instead of guessing.
    if '\"\"\"' in source:
        raise ValueError("Raw C# strings are unsupported by the automated version preflight.")
    tokens = re.compile(r'//[^\r\n]*|/\*[\s\S]*?\*/|@"(?:""|[^"])*"|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|\bconst\s+string\s+PluginVersion\s*=\s*"(?P<version>[^"\r\n]+)"\s*;')
    declarations = [match for match in tokens.finditer(source) if match.group("version") is not None]
    if len(declarations) != 1:
        raise ValueError("Expected one literal const string PluginVersion declaration.")
    return declarations[0]


def package_mod(name: str, skip_audit: bool = False) -> dict:
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
    if plugin_version_declaration(plugin_source).group("version") != metadata["version"]:
        raise ValueError("PluginVersion must agree with the package version.")
    if receipt.get("source_sha256") != source_digest(folder) or receipt.get("assembly_sha256") != sha256(dll):
        raise ValueError("Source or DLL changed since the successful build; build again before packaging.")
    lock = next((candidate for candidate in (folder / "src/packages.lock.json", folder / "packages.lock.json")
                 if candidate.is_file()), None)
    if lock is not None and not receipt.get("lock_sha256"):
        raise ValueError("A lockfile is present but the build receipt has no lock provenance; build again "
                         "(receipts older than 1.13.3 cannot vouch for the lock).")
    if lock is not None and sha256(lock) != receipt["lock_sha256"]:
        raise ValueError("packages.lock.json changed since the successful build; build again before packaging.")
    if receipt.get("package_sha256") != package_digest(folder):
        raise ValueError("Manifest, README, icon or content/ changed since the successful build, or the receipt "
                         "predates package provenance; build again before packaging.")

    # Release preflight: a package must never ship with the audit's blocking findings outstanding.
    # Warnings stay advisory; skipping the audit is allowed but reported in the result.
    audit = audit_project(folder)
    if audit["errors"] and not skip_audit:
        raise ValueError("Project audit failed (fix it, or pass --skip-audit explicitly): " + "; ".join(audit["errors"]))
    package_before = package_digest(folder)
    output = owned(ROOT / "artifacts" / f"{metadata['author']}-{name}-{metadata['version']}.zip")
    output.parent.mkdir(parents=True, exist_ok=True)

    # Snapshot every packaged byte now, after boundary validation. The archive is then written from memory,
    # so replacing a file mid-package (including the DLL) cannot put unverified bytes in a trusted ZIP.
    payload: dict[str, bytes] = {}
    budget = Budget()

    def take(archive_name: str, source: Path) -> None:
        # Boundary check first, then one verified open: the bytes come from the same handle that was checked,
        # so swapping the path to a link, or hardlinking another project's file, cannot get past this.
        resolved = project_input(folder, source)
        payload[archive_name] = read_bounded(resolved, budget, archive_name, folder)

    take("manifest.json", folder / "manifest.json")
    take("README.md", folder / "README.md")
    take("icon.png", folder / "icon.png")
    take(f"plugins/{name}/{name}.dll", dll)
    content = folder / "content"
    for item in sorted(content.rglob("*")) if content.exists() else []:
        if not item.is_file():
            continue
        if item.suffix.lower() in {".dll", ".exe", ".pdb", ".cs", ".csproj", ".py", ".ps1", ".cmd", ".bat", ".nupkg", ".zip", ".7z"}:
            raise ValueError(f"content/ is for runtime assets, not code or archives: {item.name}")
        take(f"plugins/{name}/{item.relative_to(content).as_posix()}", item)
    for license_name in ("LICENSE", "LICENSE.txt", "LICENSE.md"):
        if (folder / license_name).is_file():
            take(license_name, folder / license_name)
    if len({path.casefold() for path in payload}) != len(payload):
        raise ValueError("Package paths collide; rename content files.")
    if hashlib.sha256(payload[f"plugins/{name}/{name}.dll"]).hexdigest() != receipt.get("assembly_sha256"):
        raise ValueError("The DLL changed while packaging started; build and package again.")
    with tempfile.NamedTemporaryFile(dir=output.parent, suffix=".zip", delete=False) as stream:
        staging = Path(stream.name)
    try:
        with zipfile.ZipFile(staging, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as package:
            for archive_name, data in sorted(payload.items()):
                entry = zipfile.ZipInfo(archive_name, date_time=(2020, 1, 1, 0, 0, 0))
                entry.compress_type = zipfile.ZIP_DEFLATED
                entry.external_attr = 0o100644 << 16
                package.writestr(entry, data)
        # Read the archive back and compare every member with the snapshot: the staging file, not the
        # source tree, is what gets promoted.
        with zipfile.ZipFile(staging) as written:
            if sorted(written.namelist()) != sorted(payload):
                raise ValueError("Archive members do not match the validated payload; package again.")
            for archive_name, data in payload.items():
                if hashlib.sha256(written.read(archive_name)).hexdigest() != hashlib.sha256(data).hexdigest():
                    raise ValueError(f"Archive member {archive_name} differs from the validated bytes; package again.")
        if package_digest(folder) != package_before:
            raise ValueError("Payload files changed while the archive was written; package again.")
        result = validate(staging)
        if not result["valid"]:
            raise ValueError("; ".join(result["errors"]))
        if output.exists() and sha256(output) != result["sha256"]:
            raise ValueError("Different package bytes already exist for this version; bump the mod version.")
        os.replace(staging, output)
    finally:
        staging.unlink(missing_ok=True)
    return {**result, "archive": str(output), "build_receipt": str(folder / "build/receipt.json"),
            "audit": {"errors": audit["errors"], "warnings": audit["warnings"], "skipped": skip_audit},
            "runtime_verified": False,
            "note": "A valid archive proves packaging only; it does not show that the mod loads or works in game.",
            "publish": "not requested"}


def _repo_slug() -> str | None:
    """owner/repo from origin, for read-only CI lookups."""
    try:
        url = subprocess.run(["git", "remote", "get-url", "origin"], cwd=ROOT, capture_output=True,
                             text=True, timeout=20).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$", url)
    return f"{match.group(1)}/{match.group(2)}" if match else None


# Only these decide whether a commit is safe to release. The release workflows themselves are excluded:
# a job cannot be required to observe its own successful conclusion.
REQUIRED_CHECKS = ("Windows tests and mod builds", "CodeQL")


def _ci_state(commit: str) -> tuple[str, list[str]]:
    """Independent CI evidence for a commit: verified, failed, pending or unknown. Never trusts a receipt."""
    slug = _repo_slug()
    if not slug or not commit:
        return "unknown", []
    try:
        result = subprocess.run(["gh", "api", f"repos/{slug}/commits/{commit}/check-runs"], capture_output=True,
                                text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return "unknown", []
    if result.returncode != 0:
        return "unknown", []
    try:
        runs = json.loads(result.stdout).get("check_runs", [])
    except ValueError:
        return "unknown", []
    relevant = [run for run in runs if isinstance(run, dict)
                and any((run.get("name") or "").startswith(required) for required in REQUIRED_CHECKS)]
    names = [f"{run.get('name')}:{run.get('conclusion')}" for run in relevant]
    if not relevant:
        return "unknown", names
    if any((run.get("status") or "") != "completed" for run in relevant):
        return "pending", names
    if any((run.get("conclusion") or "") != "success" for run in relevant):
        return "failed", names
    return "verified", names


def _git_tree(commit: str) -> dict[str, str]:
    """Blob hashes of every tracked file at a commit, as Git itself computes them."""
    result = subprocess.run(["git", "ls-tree", "-r", "-z", "--full-tree", commit], cwd=ROOT,
                            capture_output=True, timeout=120)
    if result.returncode != 0:
        raise ValueError(f"Cannot read the tagged tree: {result.stderr.decode(errors='replace').strip()}")
    tree: dict[str, str] = {}
    payload = result.stdout if isinstance(result.stdout, bytes) else result.stdout.encode()
    for entry in payload.split(b"\0"):
        if not entry:
            continue
        meta, _, path = entry.partition(b"\t")
        parts = meta.split()
        if len(parts) < 3 or parts[1] != b"blob":
            continue
        tree[path.decode("utf-8", "surrogateescape")] = parts[2].decode()
    return tree


def _expected_export(commit: str, prefix: str) -> dict[str, str]:
    """The exact member bytes Git produces for a commit, keyed by path relative to the archive root.

    Git applies `.gitattributes` rules when exporting (`*.ps1 eol=crlf` and friends), so comparing against raw blobs
    would reject correct archives. Letting Git build the reference from the immutable commit — with line-ending
    conversion pinned — keeps the comparison exact without re-implementing attribute matching here.
    """
    with tempfile.TemporaryDirectory() as scratch:
        reference = Path(scratch) / "reference.zip"
        result = subprocess.run(["git", "-c", "core.autocrlf=false", "-c", "core.eol=lf", "archive",
                                 "--format=zip", f"--prefix={prefix}", commit, "-o", str(reference)],
                                cwd=ROOT, capture_output=True, timeout=300)
        if result.returncode != 0:
            raise ValueError(f"Cannot export the tagged tree: {result.stderr.decode(errors='replace').strip()}")
        tree, problems = _archive_tree(reference, prefix)
        if problems:
            raise ValueError(f"Git's own export is unusable: {problems[0]}")
        return tree


def _archive_tree(path: Path, prefix: str) -> tuple[dict[str, str], list[str]]:
    """Blob hashes of archive members, keyed by path relative to the release root directory."""
    tree: dict[str, str] = {}
    problems: list[str] = []
    with zipfile.ZipFile(path) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            name = member.filename
            if not name.startswith(prefix):
                problems.append(f"archive member outside the release root: {name}")
                continue
            data = archive.read(member)
            tree[name[len(prefix):]] = hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()
    return tree, problems


def _compare_tree(expected: dict[str, str], actual: dict[str, str]) -> list[str]:
    """Every published file must exist in the tag with identical bytes, and nothing else may be added."""
    problems: list[str] = []
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    changed = sorted(name for name in set(expected) & set(actual) if expected[name] != actual[name])
    for name in missing[:5]:
        problems.append(f"tagged file missing from the release archive: {name}")
    for name in extra[:5]:
        problems.append(f"release archive contains a file the tag does not: {name}")
    for name in changed[:5]:
        problems.append(f"release archive content differs from the tag: {name}")
    if len(missing) + len(extra) + len(changed) > 15:
        problems.append(f"{len(missing) + len(extra) + len(changed)} files differ from the tag in total")
    return problems


def _check_source_archive(path: Path, expected_files: int | None) -> list[str]:
    """A release source archive must be a real, sane ZIP, not merely a file with the right hash."""
    problems: list[str] = []
    if not zipfile.is_zipfile(path):
        return ["source archive is not a ZIP file"]
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        names = [member.filename for member in members]
        if archive.testzip() is not None:
            problems.append("source archive has a corrupt member")
        if len(members) > 20000:
            problems.append("source archive has too many members")
        if sum(member.file_size for member in members) > 2 * 1024 * 1024 * 1024:
            problems.append("source archive expands beyond 2 GiB")
        folded = [name.casefold() for name in names]
        if len(set(folded)) != len(folded):
            problems.append("source archive has duplicate members")
        for name in names:
            parts = PurePosixPath(name).parts
            if name.startswith("/") or ".." in parts or ":" in name:
                problems.append(f"unsafe member path: {name}")
        if expected_files is not None and len(members) != expected_files:
            problems.append(f"source archive has {len(members)} entries but the receipt claims {expected_files}")
    return problems


def release_check(mode: str = "prerelease", assets: str | Path | None = None) -> dict:
    """Compare every place the project's own version is written; two modes, never a silent pass.

    prerelease: a pull request or untagged main commit - a tag is optional, and its absence is reported
    as `not_required` rather than as verified. release: a real version tag, where every field and any
    supplied asset directory must agree or the gate fails.
    """
    if mode not in {"prerelease", "release"}:
        raise ValueError("mode must be 'prerelease' or 'release'")
    import ror2forge
    errors, warnings = [], []
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    package_version = ror2forge.__version__
    if not VERSION.fullmatch(version):
        errors.append(f"VERSION is not MAJOR.MINOR.PATCH: {version!r}")
    if version != package_version:
        errors.append(f"VERSION {version} != ror2forge.__version__ {package_version}")
    changelog = ROOT / "CHANGELOG.md"
    heading = None
    if not changelog.is_file():
        errors.append("CHANGELOG.md is missing")
    else:
        for line in changelog.read_text(encoding="utf-8").splitlines():
            match = re.match(r"# (\d+\.\d+\.\d+)\b", line)
            if match:
                heading = match.group(1)
                break
        if heading is None:
            errors.append("CHANGELOG.md has no '# X.Y.Z' heading")
        elif heading != version:
            errors.append(f"CHANGELOG newest heading {heading} != VERSION {version}")
    tag_name, tag_status = None, "unknown"
    try:
        result = subprocess.run(["git", "describe", "--tags", "--exact-match", "HEAD"], cwd=ROOT,
                                capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError) as exc:
        warnings.append(f"git unavailable, tag not verified: {exc}")
        result = None
    if result is not None:
        if result.returncode == 0 and result.stdout.strip():
            tag_name = result.stdout.strip()
            if not re.fullmatch(r"v\d+\.\d+\.\d+", tag_name):
                errors.append(f"tag {tag_name!r} is not a single-v vX.Y.Z tag")
                tag_status = "malformed"
            elif tag_name[1:] != version:
                # On an untagged development branch HEAD still carries the previous release tag; that is
                # expected mid-cycle, so it is a warning there and a hard error for a release gate.
                message = f"tag {tag_name} != VERSION {version}"
                tag_status = "stale" if mode == "prerelease" else "mismatch"
                (warnings if mode == "prerelease" else errors).append(message)
            else:
                tag_status = "ok"
        else:
            tag_status = "absent"
            if mode == "release":
                errors.append("no version tag points at HEAD; tagged releases require one")
    elif mode == "release":
        errors.append("cannot verify the release tag: git is unavailable")
    if mode == "prerelease" and tag_status == "absent":
        tag_status = "not_required"
    # Release assets: the published bytes themselves, never just a claim that they exist.
    asset_errors: list[str] = []
    asset_report = None
    if mode == "release" and not assets:
        # Prepublication a tag has no released files yet: this is incomplete proof, not a broken release.
        warnings.append("release assets were not checked; pass --assets to verify published bytes")
    if assets:
        folder = Path(assets)
        sums, receipts = folder / "SHA256SUMS", folder / "BUILD-RECEIPT.json"
        listed: dict[str, str] = {}
        if not sums.is_file():
            asset_errors.append("SHA256SUMS is missing")
        else:
            for raw in sums.read_text(encoding="utf-8-sig").splitlines():
                line = raw.strip()
                if not line:
                    continue
                parts = line.split(None, 1)
                if len(parts) != 2 or not re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]):
                    asset_errors.append(f"malformed checksum line: {line[:80]}")
                    continue
                digest, name = parts[0].lower(), parts[1].strip().lstrip("*")
                if name in listed:
                    asset_errors.append(f"duplicate checksum entry: {name}")
                if name.startswith(("/", "\\")) or ".." in Path(name).parts or ":" in name:
                    asset_errors.append(f"unsafe asset path: {name}")
                    continue
                listed[name] = digest
                target = folder / name
                if not target.is_file():
                    asset_errors.append(f"listed asset missing: {name}")
                elif sha256(target) != digest:
                    asset_errors.append(f"asset hash mismatch: {name}")
            if not listed:
                asset_errors.append("SHA256SUMS lists no files")
            if not any(name.endswith("-source.zip") for name in listed):
                asset_errors.append("no source archive is listed in SHA256SUMS")
        receipt: dict = {}
        if not receipts.is_file():
            asset_errors.append("BUILD-RECEIPT.json is missing")
        else:
            try:
                receipt = read_json(receipts)
            except (ValueError, OSError) as exc:
                asset_errors.append(f"BUILD-RECEIPT.json is not valid JSON: {exc}")
        if not isinstance(receipt, dict) or not receipt:
            asset_errors.append("BUILD-RECEIPT.json must be a non-empty JSON object")
            receipt = {}
        artifact: dict = {}
        if receipt:
            for key in ("commit", "artifact", "ci_checks"):
                if key not in receipt:
                    asset_errors.append(f"receipt is missing {key}")
            if not isinstance(receipt.get("artifact"), dict):
                asset_errors.append("receipt artifact must be an object")
            else:
                artifact = receipt["artifact"]
                for key in ("file", "sha256", "size_bytes", "files"):
                    if not artifact.get(key):
                        asset_errors.append(f"receipt artifact is missing {key}")
                if not isinstance(artifact.get("size_bytes"), int) or not isinstance(artifact.get("files"), int):
                    asset_errors.append("receipt artifact size_bytes/files must be integers")
            checks = receipt.get("ci_checks")
            if not isinstance(checks, list) or not checks:
                asset_errors.append("receipt lists no CI checks")
            else:
                for entry in checks:
                    if not isinstance(entry, dict) or entry.get("conclusion") != "success":
                        asset_errors.append("receipt claims CI that did not succeed")
                        break
            expected_name = f"Risk-of-Rain-2-Forge-{version}-source.zip"
            if artifact.get("file") and artifact["file"] != expected_name:
                asset_errors.append(f"receipt artifact {artifact['file']} is not this release's {expected_name}")
            if expected_name not in listed:
                asset_errors.append(f"the release does not publish {expected_name}")
            if artifact.get("file") and artifact["file"] not in listed:
                asset_errors.append("receipt artifact is not covered by SHA256SUMS")
            claimed_file = folder / str(artifact.get("file", ""))
            if artifact.get("sha256") and claimed_file.is_file():
                if sha256(claimed_file) != artifact["sha256"]:
                    asset_errors.append("receipt artifact hash does not match the published file")
                if isinstance(artifact.get("size_bytes"), int) and claimed_file.stat().st_size != artifact["size_bytes"]:
                    asset_errors.append("receipt artifact size does not match the published file")
            source = folder / expected_name
            if source.is_file():
                asset_errors.extend(_check_source_archive(source, artifact.get("files")))
                # A correct structure and checksum prove nothing about the content: compare every byte to the tag.
                tag_commit = subprocess.run(["git", "rev-parse", f"{tag_name}^{{commit}}"], cwd=ROOT,
                                            capture_output=True, text=True, timeout=30).stdout.strip()
                if not tag_commit:
                    asset_errors.append("cannot resolve the release tag to a commit, so the archive is unproven")
                else:
                    try:
                        expected = _expected_export(tag_commit, f"Risk-of-Rain-2-Forge-{version}/")
                    except ValueError as error:
                        asset_errors.append(str(error))
                        expected = None
                    if expected is not None:
                        try:
                            published, stray = _archive_tree(source, f"Risk-of-Rain-2-Forge-{version}/")
                        except (zipfile.BadZipFile, OSError, RuntimeError):
                            asset_errors.append("source archive could not be read for content comparison")
                        else:
                            asset_errors.extend(stray)
                            asset_errors.extend(_compare_tree(expected, published))
            actual = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                                    text=True, timeout=20).stdout.strip()
            if not receipt.get("commit"):
                asset_errors.append("receipt has no commit")
            elif receipt["commit"] != actual:
                asset_errors.append(f"receipt commit {receipt['commit']} != HEAD {actual}")
            asset_report = {"files": sorted(listed), "commit_claimed": receipt.get("commit"),
                            "commit_actual": actual}
    version_consistent = not errors          # only the VERSION/tag/changelog checks have run at this point
    errors.extend(asset_errors)
    tag_verified = tag_status in {"ok", "not_required"}
    assets_verified = bool(assets) and not asset_errors
    ci_state, ci_names = (_ci_state((asset_report or {}).get("commit_actual") or "")
                          if assets_verified else ("unknown", []))
    if mode == "release" and ci_state == "failed":
        errors.append("independent CI check for this commit did not succeed")
    release_verified = (not errors and tag_status == "ok" and assets_verified and ci_state == "verified")
    return {"mode": mode, "version": version, "package_version": package_version, "changelog": heading,
            "tag": tag_name, "tag_status": tag_status, "assets": asset_report,
            "checks": {"version": version_consistent, "tag": tag_verified,
                       "assets": assets_verified, "ci": ci_state},
            "ci_checks": ci_names,
            "valid": not errors,
            "release_verified": release_verified,
            "verified": release_verified,
            "errors": errors, "warnings": warnings,
            "note": "A matching version set proves the release is labelled consistently; it does not prove the code works."}


LOG_ROOTS = ("artifacts", "logs")


def _log_allowed(path: Path) -> bool:
    """A path this tool may read as a log: a discovered profile log, or a forge diagnostic log."""
    resolved = path.resolve()
    if any(Path(profile["log"]).resolve() == resolved for profile in discover()["profiles"]):
        return True
    for name in LOG_ROOTS:
        root = (ROOT / name).resolve()
        if resolved.is_relative_to(root) and resolved.suffix.lower() == ".log":
            return True
    return False


def logs(path: str | None = None, lines: int = 250) -> dict:
    if not 1 <= lines <= 5000:
        raise ValueError("Read 1–5000 trailing lines.")
    selected = Path(path).resolve() if path else None
    if selected is None:
        candidates = [Path(profile["log"]) for profile in discover()["profiles"] if Path(profile["log"]).is_file()]
        if not candidates:
            raise ValueError("No BepInEx log exists yet; launch a test profile or pass --path.")
        selected = max(candidates, key=lambda item: (item.stat().st_mtime_ns, str(item)))
    if not _log_allowed(selected):
        raise ValueError("Only discovered BepInEx logs and forge logs under artifacts/ or logs/ can be read.")
    if selected.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("Log is larger than 64 MiB; copy the tail you need instead.")
    with selected.open(encoding="utf-8-sig", errors="replace") as stream:
        tail = [line[:4000] for line in deque(stream, maxlen=lines)]
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
    mapping = {"overview": "AGENT_GUIDE.md", "code": "RECIPES.md", "content": "RECIPES.md", "assets": "RECIPES.md", "networking": "RECIPES.md", "debugging": "RECIPES.md", "character": "CHARACTER_PIPELINE.md", "audio": "AUDIO.md", "extraction": "EXTRACTION.md", "runtime": "RUNTIME.md", "thunderstore": "THUNDERSTORE.md", "checklist": "SURVIVOR_CHECKLIST.md"}
    if topic not in mapping:
        raise ValueError(f"Unknown guide topic: {topic}")
    path = ROOT / "docs" / mapping[topic]
    return {"topic": topic, "path": str(path), "text": path.read_text(encoding="utf-8")}
