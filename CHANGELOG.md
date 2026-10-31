# 1.4.0 — Audio route (2026-10-31)

- Add `docs/AUDIO.md`: the measured truth about audio in Risk of Rain 2 (Unity audio disabled, Wwise 2023.1 only), the two viable routes — a real Wwise sound bank with R2API.Sound, or an OS output stream with its spatialisation and mixer costs — and the four interop bugs that cause silence, noise bursts or a beeping exit. Includes a check-it-yourself snippet and a verification checklist that works without ears.
- `forge doctor` now reports installed Wwise authoring versions and whether a 2023.1 install is ready to generate sound banks.
- `forge guide audio` returns the new document.

# 1.3.0 — Character pipeline (2026-10-30)

- Add `docs/CHARACTER_PIPELINE.md`: the verified route for building a playable survivor from another game's assets without a Unity editor — source extraction, mesh/rig/clip conversion, baked runtime packs, the minimum working body (clone, hurtbox, camera, death state, skills, skins, `SurvivorDef`), the verification loop, failure modes and licensing. Proven on a 44-skin character shipped as a 45.9 MB package.
- Record the engine facts that cost the most time, measured on the baseline build: Unity's audio subsystem is disabled and cannot be revived (`AudioClip.Create` returns an empty clip; Wwise 2023.1 only), `CharacterModel` owns renderer visibility, skin application replaces `baseRendererInfos`, and the vanilla teardown `NullReferenceException`s that look like mod errors.
- Expose the route through the CLI as `forge guide character`; the recipes, agent guide, README, roadmap and reusable skill now route survivor work to it.
- Add a regression test that every guide topic resolves to an existing document.
- Align the reported version: `ror2forge.__version__` (what `doctor` and the MCP server report) is now locked to the `VERSION` file by a test, after the two drifted during the 1.3.0 bump.
- Voice lines remain **WIP**: the pipeline documents why custom audio needs a Wwise bank, and no runtime `AudioSource` path is recommended.

# 1.2.0 — Initial WIP prerelease (2026-10-29)

- Publish the first source-kit release with pinned tool setup, templates, agent guides, checksums and a build receipt. Third-party tools install locally; their binaries and game files are excluded.
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
