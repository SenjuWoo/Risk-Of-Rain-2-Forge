# Contributing

This is a Windows-first WIP. Small, focused bug fixes and tested modding workflows are welcome. Open an issue before a large change; describe the modding task and the evidence that the proposed tool helps.

1. Fork/clone, install Python 3.11+ and .NET 10 SDK, then run `forge.cmd setup`.
2. Run `.venv\Scripts\python.exe -m unittest discover -s tests -v`.
3. In a clean checkout, run `.venv\Scripts\python.exe scripts/ci_smoke.py` for real builds/packages. It creates CIPlugin/CIStats under projects/ and refuses to overwrite existing projects; use a clean checkout to repeat it.
4. Include a regression check for nontrivial behavior, update relevant help/docs, and describe exact validation in the PR.

Keep CLI JSON stable, stderr useful, dependencies pinned and MCP explicitly opt-in. Do not register global services or change personal agent/model settings. One writer owns each generated mod project. Installed game/profile/save folders are read-only references.

Do not commit game assemblies, decompiled source, local paths/credentials, tools caches or generated mods. Report game/Unity/loader versions and distinguish compilation from game, multiplayer and save evidence. For dependency changes, update the actual manifest/pin and regenerate local caches/locks through setup; caches stay untracked.

Original contributions are submitted under the repository's MIT license. Identify the source/license of any third-party material. Report security issues using SECURITY.md.
