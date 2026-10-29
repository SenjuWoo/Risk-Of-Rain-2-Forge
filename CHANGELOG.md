# 1.2.0 — WIP / unreleased

- Add on-demand official-feed update checks with compatibility-scoped reference candidates and explicit partial failures; no automatic upgrades or background services.
- Repair stale MCP cache/lock handling when the desired SDK pin changes, preserving working data on failed downloads/offline mismatches.
- Correct doctor build readiness for NuGet-based template builds without an installed game, checking for an SDK that supports the template language.

# 1.1.0 — WIP / unreleased

- `symbols`: bounded, case-insensitive exact type discovery through pinned ILSpy, including nested types, interfaces, structs, enums and delegates; no background index.
- `bump`: validate and back up generated mod version fields, update them together and roll back failed writes. Preserve old release packages and require a fresh build.
- Extend clean Windows CI to search compiled fixtures, inspect nested types, bump/rebuild both templates and preserve old/new packages. Keep the optional MCP schema unchanged.

# 1.0.0 — WIP / unreleased

- Public MIT source repository, clean Windows CI, Dependabot, contribution/security policies and issue templates.
- Fresh-clone setup instructions; private runtime/tool caches excluded from publication. No stable binary release.

- Local, CLI-first Risk of Rain 2 mod workbench and reusable agent playbook.
- Pinned BepInEx/Unity/GameLibs templates, optional R2API stat template, locked/offline builds.
- Local ILSpy, Thunderstore CLI, optional official-SDK MCP adapter and offline setup caches.
- Read-only discovery/type inspection/log triage/Thunderstore lookup, guarded deterministic mod packaging and ZIP validation.
- Agent recipes for content/assets/networking; MCP remains opt-in and unregistered globally.
