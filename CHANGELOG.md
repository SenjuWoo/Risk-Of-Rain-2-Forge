# 1.12.2 — Cloth on a baked rig (2026-11-04)

- `docs/RUNTIME.md` gains "Cloth on a baked rig": drive the cloth bones yourself in `LateUpdate` (`DefaultExecutionOrder` above the animation driver) from ground speed, vertical speed and turn rate, in world space, with the swing falling off by chain depth; and give the cloth a visible inside by appending a reversed-winding, flipped-normal copy of every submesh weighted to cloth bones. Measured on Odinforce Ultron's cape (3,222 -> 6,444 and 14,493 -> 28,986 vertices) with the outside unchanged.
- `docs/CHARACTER_PIPELINE.md` failure modes gained two rows: a rigid or one-sided cape, and an ultimate that lands shorter than the primary because its impact point had its own range cap.

# 1.12.1 — Dash movement and projectile ultimates (2026-11-04)

- `docs/RUNTIME.md`: a dash must move through `characterMotor.rootMotion` (the kinematic controller sweeps it), never `Motor.SetPosition` plus `velocity` — measured on Kisame 1.1.0, which passed through geometry and dropped out of the map. Also records why a hand-rolled forward `SphereCast` on top of the controller cut an 18 m rush to 7.4 m, the 15% slope headroom with a `duration * 1.2` end condition (18.29 m measured), the `hurtBoxesDeactivatorCounter` and `AddOneStock()` patterns, and why a projectile ultimate needs a per-step contact test and `FalloffModel.None` to match its tooltip.
- `docs/CHARACTER_PIPELINE.md` failure modes gained two rows for those symptoms.

# 1.12.0 — Shark sync, effect blend codes and bounded test runs (2026-11-04)

- `docs/RUNTIME.md` records three Kisame lessons: flying skill states run on every client so everyone sees the projectile while the server applies damage; Storm 4 NUD blend factors (dst 1 alpha, 2/7 additive, 3/5 reverse-subtract, high bits are flags) with per-vertex RGBA and DISABLEREMAP/VERTEXCOLOR/VERTEXALPHA materials, boost/bias 1/0, and the alpha-test reference in curve slot 16; automated game runs must be time-bounded with harness state restored in a finally (a hidden-layer throw once cost ~50 minutes).
- `docs/CHARACTER_PIPELINE.md` failure modes gained three rows for those symptoms.

# 1.11.0 — Survivor checklist (2026-11-03)

- New `docs/SURVIVOR_CHECKLIST.md`, also `forge guide checklist`: twelve defaults of a survivor (item displays, damage source, authority, clone leftovers, audio volume and distance, texture memory, package layout, R2API names, live model, buffs, costumes, tooltips) and a definition of done. Written so a weaker model reads one page and cannot skip the items that compile, validate and play solo. The agent guide, skill and `AGENTS.md` send survivor work there first.
- `docs/CHARACTER_PIPELINE.md` failure modes gained five rows: invisible items, skill items ignoring hits, T-pose after a costume swap, invented or clamped costumes, and sound that ignores the slider.
- `docs/RUNTIME.md` records Gnar's reuse of the item display recipe (own bone map, build factor 0.9, rebuild on every form swap).
- 1 regression test.

# 1.10.1 — Audit accepts Compress then Apply(false, true) (2026-11-03)

- The `LoadImage(..., false)` warning no longer fires when the source also calls `Apply(..., true)`. `Compress()` needs readable pixels and `Apply(false, true)` frees the CPU copy, so Gnar's DXT path is correct; passing `true` would make `Compress` throw and ship 4x the VRAM. Reported by the Gnar session, checked against `GnarAssets.cs`.
- 1 regression test.

# 1.10.0 — Survivor polish: item displays, damage source, audio volume (2026-11-03)

- `forge audit` warns (does not fail) on four survivor gaps that compile, validate and play solo: a registered survivor with no `itemDisplayRuleSet`, a `BulletAttack`/`BlastAttack`/`OverlapAttack` whose `damageType` is a literal `DamageType.` with no `DamageSource`, `waveOutWrite` without `AudioManager.cvVolumeSfx`, and `ImageConversion.LoadImage(..., false)`.
- `forge audit` no longer fails `using R2API.Utils;` (and `MiscHelpers`, `AutoVersionGen`): those namespaces ship in R2API.Core, so they need `R2API_Core`, not a nonexistent `R2API_Utils`. It was a false error on Ultron.
- `docs/RUNTIME.md`: item displays without an editor by sharing Commando's rule set through per-bone adapters (rotation frame, height ratio, build factor), rebuilding displays after every rig build, and the `SetEquipmentDisplay` null-inventory throw. Also: motor writes need `hasEffectiveAuthority`, attacks need a `DamageSource`, clear the cloned Commando `SfxLocator` death/bark cues, load textures non-readable, keep bake duplicates out of the package.
- `docs/AUDIO.md`: Route B code for the game's Master x SFX sliders (`AudioManager.cvVolumeMaster`/`cvVolumeSfx`) and camera-distance falloff, and scaling into the native buffer instead of a managed copy per shot.
- 5 regression tests.

# 1.9.0 — Audit catches silent audio and version drift (2026-11-03)

- `forge audit` fails every `"Play_..."` string in C# that is not a key in a shipped `events.txt`. A missing key plays nothing and throws nothing; Gnar's transform voice was silent for a release because of it.
- `forge audit` fails version drift between `manifest.json` `version_number`, any `.csproj` `<Version>` and any C# `const string ...Version`.
- `docs/AUDIO.md`: the shutdown order was wrong. Join the mixer thread before `waveOutReset`, or a buffer queued after the reset is freed while the device owns it. Five bugs now, with the event-map one added.
- `docs/CHARACTER_PIPELINE.md`: tooltip/README numbers drifting after a rebalance, %-max-health effects that need a cap against RoR2 boss pools, version-field drift, and the fact that dev runs write to the player's real Steam save.
- `docs/THUNDERSTORE.md`: ask the live API before calling a version unpublished.
- 2 regression tests (missing event key, version drift).

# 1.8.0 — Survivor runtime and the Thunderstore page (2026-11-01)

- Add `docs/RUNTIME.md`: lessons from the second played survivor. The live model is detached, so `GetComponentInParent` and `IsChildOf` miss the body. Companion aim belongs in `LateUpdate` and mesh +Z uses `LookRotation(aim)`, not the negated aim. `CharacterCameraParams.data` is a struct. A timed buff uses one stat-hook field (`moveSpeedMultAdd` or `armorAdd`) and must not stack vanilla `CloakSpeed`, vanilla `ArmorBoost`, or a second velocity multiply. Heal stays on the server.
- `docs/AUDIO.md` records that both shipped characters play 48 kHz stereo 16-bit PCM, and that the second character shipped the OS mixer without the game volume slider or pause-on-timescale. The player accepted that voice. The four mixer bugs are unchanged.
- `docs/CHARACTER_PIPELINE.md` no longer says a WAV cannot be heard. `AudioSource` still cannot. Route B can.
- Add `docs/THUNDERSTORE.md`: the zip rules `validate` already enforces, plus the page rules it cannot see. Dependency versions are minimums, the README in the zip is the page, gallery images are a separate upload, and an uploaded version cannot be edited. Records the R2API and BepInEx minimums that were active on 2026-11-01. The `forge new` pins are unchanged.
- `forge guide runtime` and `forge guide thunderstore` return the new docs.

# 1.7.0 — Extracting assets from other games (2026-11-01)

- Add `docs/EXTRACTION.md`: the route for pulling a character out of a UE4/UE5 game with CUE4Parse, the coordinate trap that twists a rig the moment it animates (mesh and animation exporters disagreeing), the `World * Bindpose == Identity` check that catches it before baking, and the 65k-vertex index limit.
- Records the measured reason Wwise banks do not transfer: RoR2 ships bank version **150 (2023.1)** while the Marvel Rivals banks extracted on this machine are **145 (2022.1)**. A bank is version-locked, so "extract a bank and drop it in" cannot work; the media can. Three honest routes are written down, including the two the shipped characters use.
- `forge guide extraction` returns it; `AGENT_GUIDE` and `AUDIO` link to it.

# 1.6.0 — Procedural geometry template (2026-11-01)

- `forge new NAME --template procedural`: a tested BepInEx plugin that generates geometry at runtime — a noise-displaced, flat-shaded icosphere with radius, subdivision and roughness exposed in the config. No Unity editor, no AssetBundle, no paid tool, no extractor. This is the same technique the Gnar boulder uses.
- Verified the way it matters: the scaffold compiles cleanly through `forge build` (0 warnings) and again in CI.
- Documented in `AGENT_GUIDE` and `CHARACTER_PIPELINE` as the first thing to try when a mod needs a shape but has no art pipeline.

# 1.5.0 — Project audit (2026-10-31)

- Add `forge audit <mod dir>`: cross-checks C# against the package manifest. Every `using R2API.<Module>` and every `[BepInDependency("com.bepis.r2api.<module>")]` must have a matching `RiskofThunder-R2API_<Module>` dependency, which is the silent "the plugin never loads for users" failure. It also warns when searchable/achievement attributes are used without `[assembly: HG.Reflection.SearchableAttribute.OptIn]`.
- Deliberately no GUID guessing for non-R2API dependencies: an early heuristic produced false positives, so those are skipped rather than reported.
- 3 regression tests, including the undeclared-module case and the namespace-import case.

# 1.4.1 — Install-layout validation (2026-10-31)

- `forge validate` now fails a package whose files sit in a top-level folder that is not an install route (`plugins`, `patchers`, `config`, `core`, `monomod`, optionally under `BepInEx/`). The Thunderstore manager empties those folders into the package root, so a ZIP that looks correct and unzips correctly can still install as loose files and break on a missing path. This shipped broken once in a character mod; the validator reported it valid.
- `docs/AGENT_GUIDE.md` states the rule and warns that a successful local unzip is not install proof.
- 4 regression tests: flat `assets/` rejected, `plugins/` route accepted, `BepInEx/plugins/` accepted, and the message names the offending folder.

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
