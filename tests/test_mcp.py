"""MCP adapter boundary tests and a real official-SDK stdio handshake.

Run with the forge .venv Python; the integration test needs forge.py in place.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

HAS_MCP = importlib.util.find_spec("mcp") is not None


@unittest.skipUnless(HAS_MCP, "Run with .venv Python after forge setup installs the official MCP SDK.")
class AdapterTests(unittest.TestCase):
    def test_fixed_executable_and_literal_arguments(self):
        from ror2forge import mcp_server
        unusual = "Type; whoami"
        with patch.object(mcp_server.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, '{"ok": true}', "")) as run:
            self.assertEqual(mcp_server.forge_inspect(unusual), {"ok": True})
            arguments, options = run.call_args
            self.assertEqual(arguments[0], [sys.executable, str(mcp_server.ROOT / "forge.py"), "inspect", unusual])
            self.assertFalse(options.get("shell", False))

    def test_cli_error_remains_mcp_error(self):
        from ror2forge import mcp_server
        from mcp.server.mcpserver.exceptions import ToolError
        with patch.object(mcp_server.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", '{"error": "missing project"}')):
            with self.assertRaisesRegex(ToolError, "missing project"):
                mcp_server.forge_build("Missing")

    def test_log_limit_is_enforced(self):
        from ror2forge import mcp_server
        from mcp.server.mcpserver.exceptions import ToolError
        with self.assertRaises(ToolError):
            mcp_server.forge_logs(lines=5001)

    def test_failed_validation_preserves_stdout_report(self):
        from ror2forge import mcp_server
        from mcp.server.mcpserver.exceptions import ToolError
        with patch.object(mcp_server.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, '{"valid": false, "errors": ["bad icon"]}', "")):
            with self.assertRaisesRegex(ToolError, "bad icon"):
                mcp_server.forge_validate("example.zip")

    def test_real_stdio_handshake_tools_resources_and_error(self):
        import anyio
        from mcp.client import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client
        root = Path(__file__).resolve().parents[1]

        async def check():
            with anyio.fail_after(45):
                parameters = StdioServerParameters(command=sys.executable, args=["-m", "ror2forge.mcp_server"], cwd=root)
                async with stdio_client(parameters) as streams:
                    async with ClientSession(*streams, read_timeout_seconds=30) as session:
                        hello = await session.initialize()
                        self.assertEqual(hello.server_info.name, "ror2-forge")
                        listing = await session.list_tools()
                        names = {tool.name for tool in listing.tools}
                        self.assertEqual(names, {"forge_doctor", "forge_new", "forge_build", "forge_inspect", "forge_package", "forge_validate", "forge_logs", "forge_lookup"})
                        guide = await session.read_resource("ror2forge://agent-guide")
                        self.assertIn("runtime", guide.contents[0].text.lower())
                        doctor = await session.call_tool("forge_doctor", {})
                        self.assertFalse(doctor.is_error)
                        content = json.loads(doctor.content[0].text)
                        self.assertIsInstance(content, dict)
                        failure = await session.call_tool("forge_logs", {"lines": 5001})
                        self.assertTrue(failure.is_error)
        anyio.run(check)


if __name__ == "__main__":
    unittest.main()
