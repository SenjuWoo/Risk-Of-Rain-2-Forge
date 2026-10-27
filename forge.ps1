# Resolve a working shared Python or the forge environment; no global settings change.
# CLI arguments are forwarded literally and diagnostics remain on stderr.
$ErrorActionPreference = 'Stop'
$candidates = @((Join-Path $PSScriptRoot '.venv\Scripts\python.exe'))
if ($env:UABS_PYTHON) { $candidates += $env:UABS_PYTHON }
if ($env:LOCALAPPDATA) {
    $pythonRoot = Join-Path $env:LOCALAPPDATA 'Python'
    if (Test-Path -LiteralPath $pythonRoot) {
        $candidates += @(Get-ChildItem -LiteralPath $pythonRoot -Directory -Filter 'pythoncore-*-64' | Sort-Object Name -Descending | ForEach-Object { Join-Path $_.FullName 'python.exe' })
    }
}
$onPath = Get-Command python -ErrorAction SilentlyContinue
if ($onPath) { $candidates += $onPath.Source }
foreach ($candidate in $candidates) {
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
    try {
        $probe = & $candidate -c 'import sys; print(int(sys.version_info >= (3, 11)))' 2>$null
        if ($LASTEXITCODE -ne 0 -or $probe -ne '1') { continue }
        & $candidate (Join-Path $PSScriptRoot 'forge.py') @args
        exit $LASTEXITCODE
    } catch [System.Management.Automation.ApplicationFailedException] { continue }
}
throw 'A working Python 3.11+ is required. Set UABS_PYTHON to its executable; setup reuses it.'
