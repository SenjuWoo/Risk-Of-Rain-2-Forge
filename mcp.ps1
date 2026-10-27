# Optional stdio server. Start only for a Risk of Rain 2 task.
# No registration, background service, or always-on server is installed.
$ErrorActionPreference = 'Stop'
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Run forge.cmd setup before starting the optional MCP adapter.' }
Push-Location -LiteralPath $PSScriptRoot
try {
    & $pythonPath -m ror2forge.mcp_server
    $serverExit = $LASTEXITCODE
} finally { Pop-Location }
exit $serverExit
