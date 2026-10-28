"""Change a generated mod's version without losing its previous source.

Needs only the standard library. Original bytes and transaction details stay in
the mod's build/version-backups/; successful builds remain separate evidence.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import tempfile
import xml.etree.ElementTree as ET

from . import core


def _unlinked(path: Path) -> Path:
    # Reject links inside the workspace too: a bump must never edit another mod.
    for ancestor in (path, *path.parents):
        if ancestor.is_symlink() or (ancestor.exists() and getattr(ancestor.lstat(), "st_file_attributes", 0) & 0x400):
            raise ValueError(f"Version changes require unlinked project paths: {ancestor}")
        if ancestor == core.ROOT:
            break
    return core.owned(path)


def _next_version(current: str, target: str) -> str:
    if not isinstance(current, str) or not core.VERSION.fullmatch(current):
        raise ValueError("The current mod version must be three numeric components.")
    numbers = tuple(map(int, current.split(".")))
    if target in {"major", "minor", "patch"}:
        index = {"major": 0, "minor": 1, "patch": 2}[target]
        bumped = list(numbers)
        bumped[index] += 1
        bumped[index + 1:] = [0] * (2 - index)
        target = ".".join(map(str, bumped))
    if not core.VERSION.fullmatch(target) or tuple(map(int, target.split("."))) <= numbers:
        raise ValueError("Choose patch, minor, major or a newer three-component version.")
    return target


def bump(name: str, target: str) -> dict:
    """Preflight all version fields, preserve originals, then replace or roll back."""
    lexical_folder = core.ROOT / "projects" / core.safe_name(name)
    _unlinked(lexical_folder)
    for relative in ("forge.json", "manifest.json", f"src/{name}.csproj", "src/Plugin.cs", "STATE.md", "CHANGELOG.md", "build/version-backups"):
        _unlinked(lexical_folder / relative)
    folder, csproj, metadata = core.project_files(name)
    manifest_path, source_path = folder / "manifest.json", folder / "src/Plugin.cs"
    manifest = core.read_json(manifest_path)
    current = metadata.get("version")
    version = _next_version(current, target)
    tree = ET.parse(csproj)
    version_nodes = tree.findall(".//Version")
    assembly_nodes = tree.findall(".//AssemblyName")
    if len(version_nodes) != 1 or len(assembly_nodes) != 1 or assembly_nodes[0].text != name:
        raise ValueError("Expected one Version and matching AssemblyName in the project.")
    for group in tree.getroot():
        if any(node.tag == "Version" for node in group) and (group.attrib or any(node.attrib for node in group if node.tag == "Version")):
            raise ValueError("Conditional/custom Version properties require a manual edit.")
    source_bytes = source_path.read_bytes()
    source = source_bytes.decode("utf-8-sig")
    declaration = core.plugin_version_declaration(source)
    if manifest.get("name") != name or manifest.get("version_number") != current or version_nodes[0].text != current or declaration.group("version") != current:
        raise ValueError("Manifest, forge.json, csproj and PluginVersion must agree before bumping.")
    project_bytes = csproj.read_bytes()
    project_text = project_bytes.decode("utf-8-sig")
    xml_tokens = re.compile(r'<!--[\s\S]*?-->|<Version>(?P<version>[^<]*)</Version>')
    properties = [match for match in xml_tokens.finditer(project_text) if match.group("version") is not None]
    if len(properties) != 1 or properties[0].group("version") != current:
        raise ValueError("Expected one plain Version property; custom XML requires a manual edit.")
    metadata = {**metadata, "version": version, "runtime_verified": False}
    manifest = {**manifest, "version_number": version}
    replacement = {
        folder / "forge.json": (json.dumps(metadata, indent=2) + "\n").encode(),
        manifest_path: (json.dumps(manifest, indent=2) + "\n").encode(),
        csproj: (project_text[:properties[0].start("version")] + version + project_text[properties[0].end("version"):]).encode("utf-8-sig" if project_bytes.startswith(b"\xef\xbb\xbf") else "utf-8"),
        source_path: (source[:declaration.start("version")] + version + source[declaration.end("version"):]).encode("utf-8-sig" if source_bytes.startswith(b"\xef\xbb\xbf") else "utf-8"),
    }
    warnings = []
    state = folder / "STATE.md"
    if state.is_file():
        text = state.read_text(encoding="utf-8-sig")
        pattern = re.compile(rf"^Version: {re.escape(current)}[ \t]*$", re.M)
        if len(pattern.findall(text)) == 1:
            text = pattern.sub(f"Version: {version}", text)
            text = re.sub(r"^Runtime:[^\r\n]*", "Runtime: unverified; version changed, retest before release.", text, flags=re.M)
            replacement[state] = (text.rstrip() + f"\n\nVersion bump: {current} → {version}; rebuild and runtime validation pending.\n").encode()
        else:
            warnings.append("Custom STATE.md version format was preserved; update its version/evidence manually.")
    changelog = folder / "CHANGELOG.md"
    if changelog.is_file():
        replacement[changelog] = (f"# {version}\n\nVersion bump from {current}; rebuild and runtime validation pending.\n\n" + changelog.read_text(encoding="utf-8-sig")).encode()
    original = {path: path.read_bytes() for path in replacement}
    backup_root = _unlinked(folder / "build/version-backups")
    backup_root.mkdir(parents=True, exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix=f"{current}-to-{version}-", dir=backup_root))
    for path, data in original.items():
        relative = path.relative_to(folder)
        saved, staged = backup / "original" / relative, backup / "staged" / relative
        saved.parent.mkdir(parents=True, exist_ok=True)
        staged.parent.mkdir(parents=True, exist_ok=True)
        saved.write_bytes(data)
        staged.write_bytes(replacement[path])
    core.write_json(backup / "transaction.json", {"from": current, "to": version, "files": [str(path.relative_to(folder)) for path in replacement], "status": "prepared"})
    changed = []
    try:
        for path in replacement:
            if path.read_bytes() != original[path]:
                raise ValueError(f"Project changed during bump; retry with one writer: {path}")
            os.replace(backup / "staged" / path.relative_to(folder), path)
            changed.append(path)
        core.write_json(backup / "transaction.json", {"from": current, "to": version, "files": [str(path.relative_to(folder)) for path in replacement], "status": "applied"})
    except BaseException:
        failed = []
        for path in reversed(changed):
            try:
                path.write_bytes(original[path])
            except OSError:
                failed.append(str(path))
        if failed:
            raise RuntimeError(f"Version bump failed; rollback incomplete for {failed}. Recover originals from {backup}")
        raise
    return {"project": str(folder), "from": current, "version": version, "backup": str(backup), "changed": [str(path.relative_to(folder)) for path in replacement], "warnings": warnings, "next": f"forge build {name} --locked", "runtime_verified": False}
