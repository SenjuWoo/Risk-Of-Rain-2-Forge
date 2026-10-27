"""Typed stdio adapter for the forge CLI using the official MCP SDK.

Needs the pinned workspace .venv. Diagnostics go to stderr; stdout belongs to MCP.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from typing import Literal

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from ror2forge import __version__

ROOT = Path(__file__).resolve().parents[1]
server = MCPServer(
    "ror2-forge", version=__version__, log_level="WARNING",
    instructions="Read ror2forge://agent-guide first. Installed games and manager profiles are read-only. Builds are not runtime proof.",
)


def _run(*arguments: str) -> dict:
    # The executable and entrypoint are fixed; arguments never pass through a shell.
    try:
        result = subprocess.run(
            [sys.executable, str(ROOT / "forge.py"), *arguments],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=600,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ToolError(str(error)) from error
    output = ((result.stderr or result.stdout) if result.returncode else result.stdout).strip()
    try:
        payload = json.loads(output)
    except json.JSONDecodeError as error:
        raise ToolError(output or f"Forge exited with code {result.returncode} without JSON.") from error
    if result.returncode:
        raise ToolError(json.dumps(payload, ensure_ascii=False))
    if not isinstance(payload, dict):
        raise ToolError("Forge returned an unexpected JSON value.")
    return payload


@server.tool()
def forge_doctor() -> dict:
    """Inspect installed RoR2, manager profiles and forge tools without changing them."""
    return _run("doctor")


@server.tool()
def forge_new(name: str, author: str, template: Literal["plugin", "stats"] = "plugin", description: str = "A Risk of Rain 2 mod.") -> dict:
    """Create a pinned mod project under projects/; refuses to replace an existing project."""
    return _run("new", name, "--author", author, "--template", template, "--description", description)


@server.tool()
def forge_build(name: str, locked: bool = False, offline: bool = False) -> dict:
    """Restore and compile an owned mod. Use locked after the initial dependency lock exists."""
    return _run("build", name, *( ["--locked"] if locked else []), *( ["--offline"] if offline else []))


@server.tool()
def forge_inspect(type_name: str, assembly: str | None = None, member: str | None = None) -> dict:
    """Use ILSpy to inspect an exact type; defaults to the installed RoR2 assembly."""
    return _run("inspect", type_name, *( ["--assembly", assembly] if assembly else []), *( ["--member", member] if member else []))


@server.tool()
def forge_package(name: str) -> dict:
    """Validate and package an owned mod for Thunderstore locally. Does not upload or deploy."""
    return _run("package", name)


@server.tool()
def forge_validate(path: str) -> dict:
    """Inspect a Thunderstore ZIP and its manifest/icon/layout without extracting or installing it."""
    return _run("validate", path)


@server.tool()
def forge_logs(path: str | None = None, lines: int = 200) -> dict:
    """Read and triage a bounded log tail; omitted path uses discovered RoR2 logs."""
    if not 1 <= lines <= 5000:
        raise ToolError("lines must be between 1 and 5000.")
    return _run("logs", "--lines", str(lines), *( ["--path", path] if path else []))


@server.tool()
def forge_lookup(namespace: str, name: str, version: str | None = None) -> dict:
    """Read one Thunderstore package's live metadata/dependencies; does not install it."""
    return _run("lookup", namespace, name, *( ["--version", version] if version else []))


@server.resource("ror2forge://agent-guide", mime_type="text/markdown")
def agent_guide() -> str:
    return (ROOT / "docs" / "AGENT_GUIDE.md").read_text(encoding="utf-8")


@server.resource("ror2forge://recipes", mime_type="text/markdown")
def recipes() -> str:
    return (ROOT / "docs" / "RECIPES.md").read_text(encoding="utf-8")


if __name__ == "__main__":
    server.run(transport="stdio")
