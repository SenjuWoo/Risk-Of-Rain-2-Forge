# Modding routes

Load only the route your task needs. Inspect the actual game's API first; a route is a checklist, not permission to invent a hook or asset address.

## Code, config and stat changes

Use the `plugin` template for a BepInEx plugin with config/logging. Use `stats` for the pinned `R2API.RecalculateStats` event example. Subscribe once and unsubscribe on destruction. For permanent stat changes, modify the stat-coefficient event arguments rather than repeatedly editing a computed field in `Update`. Verify the event signature in the referenced assembly and avoid duplicate subscriptions on scene changes. Keep per-frame and global object searches out of hot paths.

Use `On.*` hooks only after inspecting the exact MMHOOK type/signature for this game version. Call `orig` exactly as the intended behavior requires. IL hooks are a last resort: match a verified pattern, fail visibly if it is absent, and restore/dispose patches. Existing HarmonyX/MonoMod dependencies belong to the loader stack; adding a second arbitrary Harmony runtime can create conflicts.

## Items, equipment, buffs, survivors and stages

Choose only the required modules: examples include R2API.ContentManagement, Items, Language, Prefab, Networking and Skins. Check current package metadata and source before selecting versions or plugin GUIDs. The entire R2API metapackage is not a default dependency.

Create definitions/prefabs and register them during the current content-provider/content-pack lifecycle before catalogs finalize. Do not append to frozen catalogs during a run. Inspect `IContentPackProvider`, `ContentManager`, and the relevant R2API module to establish the exact registration API. Pair localization tokens with definitions. Validate pickup/display rules, icon/material references, unlock conditions, logbook visibility and dropped-item behavior. Asset addresses and catalog indices are not stable identifiers to guess.

Use the game’s existing shaders/material conventions and verified Addressables paths. The 1.5.0 migration changed equipment storage, projectile ghosts and some hooks, and obsoleted `CharacterBody.ItemBehavior`; inspect current replacement APIs rather than porting old snippets mechanically.

## Assets and Unity

Code-only mods need no Unity editor. For AssetBundles, models, animation, audio or custom UI, discover the installed Unity editor and match the game's required editor version. The observed runtime is `2021.3.45f2`; [R2Wiki's Unity page](https://risk-of-thunder.github.io/R2Wiki/Mod-Creation/Unity-Version/) is the current upstream check. Use Built-in rendering; URP/HDRP is not a drop-in RoR2 mod pipeline.

[RoR2EditorKit](https://github.com/risk-of-thunder/RoR2EditorKit/releases) tagged `5.7.1` was observed during research. [ThunderKit](https://risk-of-thunder.github.io/R2Wiki/Mod-Creation/ThunderKit/Crash-Course-and-Getting-Started/) and RoR2 import extensions automate the asset project/import workflow. Resolve a supported immutable release or commit against the chosen Unity editor before installing. Do not automatically import the game or configure a Unity MCP without an actual editor project and running bridge. The forge does not claim to bundle Unity or certify these optional editor imports.

Import owned assets into a separate authoring project, build the bundle for the target platform, then place produced runtime bundles/audio/etc. in `projects/NAME/content/` before building. Packaging preserves their paths under `plugins/NAME/` and includes an optional project LICENSE. It refuses extra DLLs, scripts and nested archives there. Test shader availability, scale, rig, animation, collisions, effects and UI at runtime. Do not distribute extracted game content as original work.

## Networking

Classify the feature: local UI/cosmetic, server-authoritative gameplay, or synchronized content. Changes to damage, drops, inventories, spawns or run state generally need server authority. Inspect the current `NetworkServer.active`/network API before implementing it; use the game's networking generation, not a modern Unity networking package chosen by name.

Register networked prefabs and message IDs through the appropriate verified APIs before use. Declare real client/server requirements and dependency versions. Test solo, host plus client, late join/reconnect where supported, dedicated server where relevant, and mismatched dependency handling. A `NetworkCompatibility` attribute or successful host session alone does not prove all clients agree.

## Debugging and performance

Use `forge.cmd logs` or `forge.cmd logs --path <BepInEx-LogOutput.log> --lines 300`. Read the first causal exception and adjacent stack trace; missing dependencies, stale hook signatures and asset load failures are different failures. Correlate the timestamp with the exact package/game build. The log command is triage, not a full crash diagnosis.

Start with the minimal plugin in a disposable profile, then add one feature/dependency at a time. For performance claims, measure a representative run before and after; avoid noisy per-frame logs. Keep normal diagnostics concise and debug output opt-in. Use the existing game profiler/debug tooling only when its version and runtime integration are verified.

## Packaging and publication

The ZIP root needs `manifest.json`, UTF-8 `README.md`, and a 256×256 PNG `icon.png`; package names use letters, digits and underscores, version is three numeric components, description is at most 250 characters, and dependencies use `Team-Package-Version`. `website_url` is required and may be empty. Use the forge validator rather than trusting this prose alone.

Build from locked dependencies and package the mod's own DLL/content, never the entire build directory. Exclude game/Unity/loader references, source bookkeeping, tests, logs, caches and backups. Retain licenses required by distributed dependencies. Keep API keys outside projects and never put a publish token in a manifest or tool argument. Publication is a separate human-authorized action; the forge produces a local candidate.
