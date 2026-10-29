# Validation history

## 1.2.0 WIP — tooling freshness and recovery

- Initial source-kit release (2026-10-29): [v1.2.0](https://github.com/SenjuWoo/Risk-Of-Rain-2-Forge/releases/tag/v1.2.0) targets green commit `93dbf201525d9089bfd498c3e9cec379f4345cab`. Two clean archives were byte-identical. Validated ZIP CRCs, source identity, version/license, exact 48-file tracked payload and exclusion of private/binary files. Exercised the extracted Windows entrypoint, doctor/guide, clean setup and the real plugin/stats build/package/inspect/bump smoke workflow. Downloaded all three published assets and verified nonzero size and SHA-256 against local builds. Evidence is in artifacts/initial-release/ and the published BUILD-RECEIPT.json/SHA256SUMS. Game/editor/runtime checks remain unperformed.
- Remote integration (2026-10-29): [PR #4](https://github.com/SenjuWoo/Risk-Of-Rain-2-Forge/pull/4) passed all four required checks and merged as `a34509fe28866f873c7169c1b32c2c21d0d4437a`. That main commit also passed [Windows CI](https://github.com/SenjuWoo/Risk-Of-Rain-2-Forge/actions/runs/40910675108) and all three [CodeQL analyses](https://github.com/SenjuWoo/Risk-Of-Rain-2-Forge/actions/runs/40910674482). Post-merge open Dependabot/code-scanning/secret-scanning queries returned 0/0/0. Local main synced without conflicts; protection was retained.
- Full `.venv\Scripts\python.exe -m unittest discover -s tests -v`: **80 tests**, exit 0, including real MCP transport. Logs: artifacts/health-tests.*. `.venv\Scripts\python.exe -m compileall -q ror2forge scripts tests`: exit 0.
- `forge.cmd updates`: exit 0, complete true, updates_available 0, all six tracked pins current according to official metadata. Evidence: artifacts/health-updates-live.json. Tests cover unsorted/prerelease versions, GameLibs revisions, excluded Unity/loader generations, malformed/oversized responses, partial feed failures and CLI exit/report preservation.
- `forge.cmd setup --offline`: exit 0, correct MCP/ILSpy/TCLI versions. Python executable mtime stayed unchanged: the healthy environment was reused. Evidence: artifacts/health-offline-setup.json. Pin-change fixture tests prove stale offline rejection, failed-download preservation, staged successful refresh with backups and cache-swap rollback. No unrequested different MCP release was installed; pip installation is not a complete environment transaction.
- Doctor tests separate game-free build capability from inspection and SDK inventory. Independent review reproduced an unavailable SDK selected by global.json despite newer SDKs being installed; readiness now uses `dotnet --version` from the forge root and reports resolution errors. Project-local overrides are still evaluated by the actual project build. Live report: artifacts/health-doctor-live.json.
- Existing template code, compile reference pins, NuGet config and build/package logic were unchanged. Prior real build/package proof remains valid; protected-main CI still performs fresh setup, 80 tests and both full template smoke workflows on every PR/main commit.
- Audit sources: official [ILSpy feed](https://api.nuget.org/v3-flatcontainer/ilspycmd/index.json), [TCLI feed](https://api.nuget.org/v3-flatcontainer/tcli/index.json), [MCP PyPI metadata](https://pypi.org/pypi/mcp/json), [BepInEx service index](https://nuget.bepinex.dev/v3/index.json), [R2Wiki Unity guidance](https://risk-of-thunder.github.io/R2Wiki/Mod-Creation/Unity-Version/) and [assembly reference guidance](https://risk-of-thunder.github.io/R2Wiki/Mod-Creation/C%23-Programming/Assembly-References/). RoR2BepInExPack 1.49.0 and R2API.RecalculateStats 1.7.0 also remain latest in their current Thunderstore metadata.
- Game/host-client/editor validation remains unperformed; existing NU1701 and third-party redistribution limits remain documented. No game/profile/config/model changes or global server registration.

## 1.1.0 WIP — symbol discovery and version iteration

### Remote convergence and resume audit — 2026-10-29

- Feature [PR #2](https://github.com/SenjuWoo/Risk-Of-Rain-2-Forge/pull/2) is merged. Exact merge SHA `28b917d6a8c611c5b7a94c825a12101990ebc2a3`: [CI passed](https://github.com/SenjuWoo/Risk-Of-Rain-2-Forge/actions/runs/40624926248), [CodeQL passed](https://github.com/SenjuWoo/Risk-Of-Rain-2-Forge/actions/runs/40624925628).
- Reviewed newer upstream `ed005418fcb7f12f4928cf9512750cec83dc3de3` before keeping it: only .github/workflows/ci.yml changed, updating three immutable official Actions pins through Dependabot PR #1. [CI passed](https://github.com/SenjuWoo/Risk-Of-Rain-2-Forge/actions/runs/40803108409), [CodeQL passed](https://github.com/SenjuWoo/Risk-Of-Rain-2-Forge/actions/runs/40803107980); all four required check-runs returned completed/success on that exact SHA.
- Clean local checkout fast-forwarded to the reviewed upstream. Retained local 55-test and real smoke logs were inspected; unchanged implementation was not rebuilt redundantly. Fresh Dependabot, code-scanning and secret-scanning alert queries each exited successfully with zero open alerts. Main remains PR-protected, including administrators.

### Local implementation evidence

- Full `.venv\Scripts\python.exe -m unittest discover -s tests -v`: **55 tests**, exit 0. Includes the real official MCP transport; no new MCP tools or global registration. Local logs: artifacts/iteration-tests.*.
- `.venv\Scripts\python.exe scripts/ci_smoke.py`: exit 0 after final shared-parser fix. Both templates compile a fixture containing class/nested class/interface/struct/enum/delegate types, discover all through installed ILSpy, and decompile the nested type. The smoke test deliberately removes whitespace around PluginVersion to verify interoperability.
- Both fixtures build online, rebuild locked/offline with identical assembly hashes, package reproducibly, bump 1.0.0 to 1.0.1, reject packaging before rebuilding, then rebuild/package successfully while retaining the previous ZIP. Logs: artifacts/iteration-ci-smoke.*. Original smoke fixtures/output preserved separately; no user mods or profiles were overwritten.
- `forge.cmd symbols RoR2.CharacterBody --limit 5`: exit 0 against the installed assembly. 25 matches, 5 returned, truncation true, exact type first; assembly SHA256 remains `48f2758cccbe1a5efba88cffe0a68631953f489a71a92726572c15a4c57ff90c`. Evidence: artifacts/symbols-live-proof.json.
- Unit tests inject replacement/final-receipt failures and confirm byte-for-byte source rollback and retained backups. They also exercise manifest mismatch, duplicate/custom declarations, comment/string decoys, BOM/CRLF preservation, prior-artifact preservation and invalid targets. Unsupported raw C# string delimiters are refused by automated version preflight rather than guessed.
- Independent review reproduced a spacing mismatch between bump and package preflight; both now use the same declaration parser, with positive spacing and negative comment-decoy regressions. No additional blockers were found in the scoped review.
- Local bumped ZIP hashes: CIPlugin 1.0.1 `8b003e88107fa62802e400bb551189837e6ee4e4c4169b1b133f2d406cad0d8f`; CIStats 1.0.1 `d40a7d3544b1c25f5969866ef01b9ea690c175589a395dbe25f327dab028a35f`. These fixtures are private evidence, not public runtime-certified mods.
- Game/Unity/host-client tests remain **not run**; MMHOOK's existing NU1701 warning remains visible. WIP source uses PR-required CI/CodeQL; exact remote checks are recorded by GitHub for each pushed SHA. No stable release is produced.

## 1.0.0 baseline — 2026-10-27

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
- TCLI is locally installed/version-tested; the guarded deterministic packager is the default. TCLI upload was never used. Its public redistribution permission is unverified; no public binary forge archive was created; the subsequent WIP publication contains source only.
- Receipts record HTTPS sources and observed hashes, not independent vendor signatures. Personal feeds/credentials/settings were not copied.

## Primary sources

- [R2Wiki reference workflow](https://risk-of-thunder.github.io/R2Wiki/Mod-Creation/C%23-Programming/Assembly-References/), [Unity version](https://risk-of-thunder.github.io/R2Wiki/Mod-Creation/Unity-Version/), [API migration](https://risk-of-thunder.github.io/R2Wiki/Mod-Creation/Updating-Your-Mods/Updating-Core-API-Changelog-1.5.0/).
- [R2API](https://github.com/risk-of-thunder/R2API), [BepInEx](https://docs.bepinex.dev/v5.4.21/), [ILSpy live metadata](https://api.nuget.org/v3-flatcontainer/ilspycmd/index.json), [TCLI metadata](https://api.nuget.org/v3-flatcontainer/tcli/index.json), [MCP metadata](https://pypi.org/pypi/mcp/json).
- [Thunderstore requirements](https://wiki.thunderstore.io/mods/creating-a-package), [actual stats package API](https://thunderstore.io/api/experimental/package/RiskofThunder/R2API_RecalculateStats/1.7.0/).

## Public WIP repository

Public MIT source publication authorized 2026-10-27. CI installs official pinned tools on a clean Windows runner, runs all tests and compiles/packages both templates without a game installation. Remote exact-SHA result is recorded in the publication handoff after verification. Local evidence artifacts listed above are deliberately untracked and are not shipped by cloning.


## First public source verification

Commit `86d28d16ee14d1d41b462080eedc9b605e605234`: [clean Windows CI](https://github.com/SenjuWoo/Risk-Of-Rain-2-Forge/actions/runs/40588483635) and [CodeQL](https://github.com/SenjuWoo/Risk-Of-Rain-2-Forge/actions/runs/40588505433) completed successfully. All 33 tests, online/locked-offline builds for both templates, deterministic packages and the Windows launcher passed on the clean runner. CodeQL analysis records match that SHA with no analysis errors. Dependabot, code-scanning and secret-scanning queries each returned zero open alerts. Public/MIT/main, dependency alerts/security updates, private vulnerability reporting and secret scanning/push protection were read back from GitHub. Code quality setup/findings returned 404 and were left off. No release/tag or third-party binary upload was made. Subsequent commits are checked by the same CI; consult Actions for the current HEAD.
