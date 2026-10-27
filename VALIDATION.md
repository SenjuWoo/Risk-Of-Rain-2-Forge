# Validation — 1.0.0, 2026-10-27

| Gate | Result |
|---|---|
| Scope/ownership | PASS — local source/outputs; game, managers, saves and shared references read only |
| Independent review | PASS — fixed stale-input hashing, namespace keywords, true stat multiplier, PNG integrity, manifest limits and MCP errors |
| Tests | PASS — 33 tests, 0 failures/skips in final SDK environment |
| Compiler | PASS — actual BepInEx plugin and R2API stats template, netstandard2.1, SDK 10.0.403 |
| Offline tools/build | PASS — fresh tools restored from caches; both templates built locked offline |
| Packages | PASS — deterministic ZIPs; required metadata/icon/own DLL only; asset and failure tests pass |
| MCP | PASS — real SDK initialize, eight tools, resource, doctor call and error propagation; opt-in/unregistered |
| Game/editor runtime | NOT RUN — no game/plugin load, gameplay, multiplayer, save or Unity editor import claims |

The local workbench delivery passes its tool/build/package gates. Mod runtime testing remains a separate gate.

## Commands and evidence

- `.venv\Scripts\python.exe -m unittest discover -s tests -v` — exit 0, **33 tests**. Saved in artifacts/tests.*. MCP requires local socketpair capability; the restricted sandbox blocked AnyIO loop initialization, so this check ran with that restriction lifted, using the same source/SDK.
- `.venv\Scripts\python.exe -m compileall -q ror2forge tests` — exit 0 before final PNG tightening; final tests imported/executed the tightened code.
- `forge.cmd doctor` — exit 0; artifacts/doctor-proof.json. Steam build 25921972, Unity 2021.3.45f2, Default/Woo profiles, local tools and real .NET SDKs. Manifest presence is not plugin load proof.
- `forge.cmd build ForgeSmoke` and `forge.cmd build ForgeStatsSmoke` — official feed restores/builds exit 0. Exact transitive resolutions/content hashes retained in src/packages.lock.json.
- `forge.cmd build ForgeSmoke --locked --offline` and `forge.cmd build ForgeStatsSmoke --locked --offline` — exit 0. Final JSON: artifacts/plugin-build-proof.json and stats-build-proof.json. Stats emits NU1701 for MMHOOK's .NET Framework asset; warning remains visible, not suppressed.
- `forge.cmd package ForgeSmoke`, `forge.cmd package ForgeStatsSmoke`, and `forge.cmd validate <each ZIP>` — exit 0, repeated output hashes identical. JSON: artifacts/*-package-proof.json. Both ZIPs revalidated after final PNG changes.
- `forge.cmd inspect RoR2.RoR2Application` and `forge.cmd inspect RoR2.RoR2Application --member M:RoR2.RoR2Application.Awake` — exit 0. Private proof: artifacts/inspect-application.json and inspect-member.json. Single member returns 1,095 characters.
- `forge.cmd lookup RiskofThunder R2API_RecalculateStats --version 1.7.0` — exit 0, real response in artifacts/lookup-proof.json.
- `forge.cmd setup --offline` — exit 0/idempotent. Fresh isolated offline restore also passed using retained NuGet archives/wheels: artifacts/toolchain-offline-proof.json. Duplicate test installation removed afterward.
- `forge.cmd new class --author Local` and offline build — exit 0, artifacts/keyword-build.json. Deliberately invalid C# then returned exit 1, structured diagnostics and persisted build.log: artifacts/failed-build-proof.json. Temporary project removed afterward.
- `forge.cmd --help` and `forge.cmd guide overview` — exit 0 through the Windows PowerShell launcher in the real workspace path containing spaces.

## Final mod artifacts

| Artifact | SHA256 |
|---|---|
| artifacts/Local-ForgeSmoke-1.0.0.zip | b455fba66d215147f82d17d20837199cd92872ab2252cd441684b90fd40ed865 |
| artifacts/Local-ForgeStatsSmoke-1.0.0.zip | f33f0de1c9df67ec526400f87f501b23a943227a1d6145c94a7f115d4d175af6 |

Each contains root README.md, icon.png, manifest.json and plugins/NAME/NAME.dll. Icons are original placeholders. Tests separately cover runtime asset packaging, duplicate/unsafe paths, malformed metadata, incomplete/corrupt PNGs, preserved release bytes, changed source/DLL rejection and source overwrite prevention.

## Baseline and exact limits

- RoR2.dll SHA256: `48f2758cccbe1a5efba88cffe0a68631953f489a71a92726572c15a4c57ff90c`.
- Installed R2API.RecalculateStats 1.7.0 inspection confirmed GUID `com.bepis.r2api.recalculatestats`, `StatHookEventArgs.moveSpeedTotalMult = 1f`, and multiplication in the injected IL. Template multiplies that value and unsubscribes its event.
- Publicized/stripped compile references do not grant private-member runtime access. Runtime APIs/hooks/network behavior still require per-mod testing.
- Source receipts cover project inputs and conventional ancestor build settings. Arbitrary external MSBuild imports, hostile build scripts, concurrent input races, future game patches and other platforms were not certified. Keep owned source trusted and one writer per project.
- No editor/EditorKit/ThunderKit MCP was registered without an editor project. Asset authoring route is documented; actual matching editor/import workflow remains task-specific.
- TCLI is locally installed/version-tested; the guarded deterministic packager is the default. TCLI upload was never used. Its public redistribution permission is unverified; no public forge archive/repository was created.
- Receipts record HTTPS sources and observed hashes, not independent vendor signatures. Personal feeds/credentials/settings were not copied.

## Primary sources

- [R2Wiki reference workflow](https://risk-of-thunder.github.io/R2Wiki/Mod-Creation/C%23-Programming/Assembly-References/), [Unity version](https://risk-of-thunder.github.io/R2Wiki/Mod-Creation/Unity-Version/), [API migration](https://risk-of-thunder.github.io/R2Wiki/Mod-Creation/Updating-Your-Mods/Updating-Core-API-Changelog-1.5.0/).
- [R2API](https://github.com/risk-of-thunder/R2API), [BepInEx](https://docs.bepinex.dev/v5.4.21/), [ILSpy live metadata](https://api.nuget.org/v3-flatcontainer/ilspycmd/index.json), [TCLI metadata](https://api.nuget.org/v3-flatcontainer/tcli/index.json), [MCP metadata](https://pypi.org/pypi/mcp/json).
- [Thunderstore requirements](https://wiki.thunderstore.io/mods/creating-a-package), [actual stats package API](https://thunderstore.io/api/experimental/package/RiskofThunder/R2API_RecalculateStats/1.7.0/).

## Public WIP repository

Public MIT source publication authorized 2026-10-27. CI installs official pinned tools on a clean Windows runner, runs all tests and compiles/packages both templates without a game installation. Remote exact-SHA result is recorded in the publication handoff after verification. Local evidence artifacts listed above are deliberately untracked and are not shipped by cloning.

