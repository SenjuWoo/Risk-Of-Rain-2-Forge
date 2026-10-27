@echo off
rem Windows CLI entrypoint; no installation, server, or global configuration.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0forge.ps1" %*
exit /b %errorlevel%
