"""On-demand version checks against official feeds; never install or change pins.

Uses only the standard library. Network failures remain explicit unknown results,
and newer reference packages still require review against the installed game.
"""
from concurrent.futures import ThreadPoolExecutor
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from . import __version__, core, toolchain

NUGET = "https://api.nuget.org/v3-flatcontainer/"
BEPINEX_INDEX = "https://nuget.bepinex.dev/v3/index.json"
PYPI = "https://pypi.org/pypi/mcp/json"
MAX_RESPONSE = 2 * 1024 * 1024


def _json(url):
    request = urllib.request.Request(url, headers={"User-Agent": f"RoR2Forge/{__version__}", "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=20) as response:
        data = response.read(MAX_RESPONSE + 1)
    if len(data) > MAX_RESPONSE:
        raise ValueError("Package metadata exceeds the 2 MiB inspection limit.")
    result = json.loads(data)
    if not isinstance(result, dict):
        raise ValueError("Package metadata must be a JSON object.")
    return result


def _version_key(version):
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+){1,3})(?:-([A-Za-z0-9]+(?:[.-][A-Za-z0-9]+)*))?(?:\+[A-Za-z0-9.-]+)?", version)
    if not match:
        raise ValueError(f"Unrecognized package version: {version}")
    release = tuple(map(int, match[1].split(".")))
    release += (0,) * (4 - len(release))
    prerelease = tuple((0, int(part)) if part.isdigit() else (1, part.casefold()) for part in re.split(r"[.-]", match[2] or ""))
    return release, match[2] is None, prerelease


def _bepinex_base():
    configured = [entry.get("value") for entry in ET.parse(core.ROOT / "NuGet.Config").findall("./packageSources/add")]
    if BEPINEX_INDEX not in configured:
        raise ValueError("The official BepInEx source is not configured in NuGet.Config.")
    resources = _json(BEPINEX_INDEX).get("resources")
    if not isinstance(resources, list):
        raise ValueError("BepInEx service index has no resources list.")
    candidates = [resource.get("@id") for resource in resources if isinstance(resource, dict) and resource.get("@type") == "PackageBaseAddress/3.0.0"]
    if len(candidates) != 1 or not isinstance(candidates[0], str):
        raise ValueError("Expected one BepInEx PackageBaseAddress/3.0.0 resource.")
    address = urllib.parse.urlsplit(candidates[0])
    if address.scheme != "https" or address.netloc != "nuget.bepinex.dev" or address.query or address.fragment:
        raise ValueError("BepInEx package endpoint must remain on its official HTTPS host.")
    return candidates[0].rstrip("/") + "/"


def _select(package, pinned, versions):
    if not isinstance(versions, list) or not versions or any(not isinstance(value, str) for value in versions):
        raise ValueError("Expected a nonempty list of package versions.")
    parsed = [(version, _version_key(version)) for version in versions]
    pin = _version_key(pinned)
    if not any(key == pin for _, key in parsed):
        raise ValueError("Pinned version is absent from the official feed.")
    if package == "RiskOfRain2.GameLibs":
        # These official reference revisions intentionally use NuGet prerelease syntax.
        candidates = [(version, key) for version, key in parsed if key[1] or re.fullmatch(r"[0-9.]+-r\.[0-9]+", version, re.I)]
        policy = "Stable game references and r.N revisions; verify the target game build before changing."
    else:
        candidates = [(version, key) for version, key in parsed if key[1]]
        policy = "Latest stable release."
    if package == "BepInEx.Core":
        candidates = [(version, key) for version, key in candidates if key[0][0] == pin[0][0]]
        policy = f"Stable BepInEx major {pin[0][0]}; other loader generations are excluded."
    elif package == "UnityEngine.Modules":
        candidates = [(version, key) for version, key in candidates if key[0][:2] == pin[0][:2]]
        policy = f"Stable Unity {pin[0][0]}.{pin[0][1]} reference line; match the installed editor/runtime before changing."
    if not candidates or not any(key == pin for _, key in candidates):
        raise ValueError("Pinned version falls outside this package's comparison policy.")
    latest, latest_key = max(candidates, key=lambda item: item[1])
    return {"latest": latest, "status": "current" if latest_key == pin else "update_available", "policy": policy}


def _check(job):
    package, pinned, source, prior_error = job
    result = {"package": package, "pinned": pinned, "source": source}
    try:
        if prior_error:
            raise ValueError(prior_error)
        metadata = _json(source)
        if package == "mcp":
            releases = metadata.get("releases")
            if not isinstance(releases, dict):
                raise ValueError("PyPI metadata has no releases object.")
            published = metadata.get("info", {}).get("version")
            if not isinstance(published, str) or not re.fullmatch(r"[0-9]+(?:\.[0-9]+){1,3}", published):
                raise ValueError("Current PyPI release has no supported numeric stable version; review it manually.")
            versions = [version for version, files in releases.items() if re.fullmatch(r"[0-9]+(?:\.[0-9]+){1,3}", version) and isinstance(files, list) and any(isinstance(file, dict) and not file.get("yanked", False) for file in files)]
            if published not in versions:
                raise ValueError("Current PyPI release has no available unyanked files.")
        else:
            versions = metadata.get("versions")
        return {**result, **_select(package, pinned, versions)}
    except Exception as error:
        return {**result, "latest": None, "status": "unknown", "error": str(error)[:500]}


def check_updates() -> dict:
    """Return a bounded, read-only update report; unknown results are not current."""
    jobs = [(package, version, f"{NUGET}{package.lower()}/index.json", None) for package, version in toolchain.DOTNET_TOOLS.items()]
    jobs.append(("mcp", toolchain.MCP_VERSION, PYPI, None))
    try:
        base, error = _bepinex_base(), None
    except Exception as problem:
        base, error = None, str(problem)[:500]
    jobs.extend((package, version, f"{base}{package.lower()}/index.json" if base else BEPINEX_INDEX, error) for package, version in core.PINS.items())
    with ThreadPoolExecutor(max_workers=4) as executor:
        entries = list(executor.map(_check, jobs))
    return {"complete": all(entry["status"] != "unknown" for entry in entries),
            "updates_available": sum(entry["status"] == "update_available" for entry in entries),
            "entries": entries, "read_only": True,
            "note": "Newer does not prove compatible. Review release notes, game/editor versions and build/runtime tests before updating pins."}
