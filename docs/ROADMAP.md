# WIP roadmap

## Working foundation

- JSON CLI, optional eight-tool MCP adapter and reusable agent skill.
- Local pinned tool provisioning, offline caches, two C# templates and NuGet locks.
- Exact assembly inspection, read-only discovery/log triage and deterministic guarded packaging.
- Tests plus clean-runner template compilation/package CI.
- Bounded symbol search through ILSpy and backed-up version bumps for the edit/build/package loop (1.1.0 WIP).

## Before a stable release

- Record repeatable BepInEx loader/gameplay checks against a named game build.
- Test stats/config changes on a host and client; document network requirements.
- Validate a real matching-Unity asset authoring/import/bundle workflow.
- Resolve or clearly scope MMHOOK's NU1701 compatibility warning with runtime evidence.
- Exercise setup/recovery on additional clean Windows machines and follow package-feed drift.

## Deliberately optional

Editor bridges, paid asset APIs and other MCP servers are enabled only for a concrete RoR2 task. Public source does not bundle game files or third-party tool binaries; redistribution terms must be checked before any binary release. No stable release date is promised.
