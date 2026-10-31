# WIP roadmap

## Working foundation

- JSON CLI, optional eight-tool MCP adapter and reusable agent skill.
- Local pinned tool provisioning, offline caches, two C# templates and NuGet locks.
- Exact assembly inspection, read-only discovery/log triage and deterministic guarded packaging.
- Tests plus clean-runner template compilation/package CI.
- Bounded symbol search through ILSpy and backed-up version bumps for the edit/build/package loop (1.1.0 WIP).
- On-demand dependency freshness reports, MCP cache recovery and game-free build diagnostics (1.2.0 WIP).
- Verified survivor/character route without a Unity editor: source extraction → mesh/rig/clip conversion → baked runtime packs → body, skins and packaging, with engine facts and failure modes (`docs/CHARACTER_PIPELINE.md`, 1.3.0).

## Before a stable release

- Record repeatable BepInEx loader/gameplay checks against a named game build.
- Test stats/config changes on a host and client; document network requirements.
- Validate a real matching-Unity asset authoring/import/bundle workflow.
- Resolve or clearly scope MMHOOK's NU1701 compatibility warning with runtime evidence.
- Exercise setup/recovery on additional clean Windows machines and follow package-feed drift.
- Exercise the character route on a second character and a second source game to separate League-specific steps from the general ones.

## Deliberately optional

Editor bridges, paid asset APIs and other MCP servers are enabled only for a concrete RoR2 task. Public source does not bundle game files or third-party tool binaries; redistribution terms must be checked before any binary release. No stable release date is promised.

## Next expansion priorities

1. Capture repeatable loader/gameplay and host/client evidence for existing templates in a deliberately selected test profile.
2. Add item/content templates only after verifying current content-provider registration, module GUIDs and multiplayer behavior; avoid stale copied boilerplates.
3. Validate a matching-Unity EditorKit/ThunderKit asset project, including import/build/runtime shader checks, before automating it.
4. Replace restricted literal version editing with compiler-aware editing when supporting complex custom source (including raw C# strings) becomes a scoped requirement.
