# Agent entrypoint

Read root `AGENTS.md`, `STATE.md`, and `WORKSPACE_OWNERSHIP.md` before writing. The forge is a local modding workbench, not a runtime compatibility certificate. Work in `projects/<Name>`; installed games, mod-manager profiles/caches and saves are reference inputs.

## Fast path

1. Run `forge.cmd doctor`. Resolve missing required capabilities before proceeding. Read the game build, Unity runtime and installed packages; never infer compatibility from a package name.

   When refreshing tooling or diagnosing version drift, run `forge.cmd updates`. It queries official feeds only on demand, reports compatibility-scoped candidates and unknown failures, and never changes pins. Do not upgrade Unity/BepInEx major lines simply because a feed has a larger number. Doctor build readiness needs a compatible SDK, not an installed game; inspection/testing still needs the actual game or an explicit DLL.
2. Choose `forge.cmd new MyMod --author MyTeam --template plugin` for plain code/config or `--template stats` for the tested R2API stat-event example. Open the generated source, manifest and lock files. For a **new survivor/character**, read `docs/CHARACTER_PIPELINE.md` before writing code (and `docs/AUDIO.md` before adding sound): it has the verified body recipe, the asset-baking pipeline for machines without a Unity editor, and the failure modes that are expensive to rediscover.
3. Find types with `forge.cmd symbols CharacterBody --limit 10`, then verify the API/hook with `forge.cmd inspect RoR2.CharacterBody`. Both accept `--assembly <path-to-dll>` for an R2API/Unity/mod assembly. Inspection accepts `--member <XML-doc-ID>` to return one member. Respect the symbol result's truncation flag; refine the query instead of requesting a whole-game source dump. Inspection output remains private.
4. Use the smallest R2API module needed; align its NuGet reference, `[BepInDependency]`, and Thunderstore manifest dependency. Add an exact version, restore once, then retain `packages.lock.json` and use `forge.cmd build MyMod --locked`.
5. Build, inspect errors, fix the cause, then `forge.cmd package MyMod` and `forge.cmd validate <zip>`. For an update, `forge.cmd bump MyMod patch` (or minor/major/increasing X.Y.Z) backs up and aligns the four version fields, preserves prior packages and invalidates the old build. Inspect its backup receipt, rebuild and review every runtime payload file. The tool refuses inconsistent/custom declarations instead of silently changing them.
6. For runtime testing, prepare a separate disposable r2modman profile and have the human select/import the package. The forge does not write to profiles, install mods, launch games, upload packages, or change personal agent settings. Record loader version, game build, package versions, log evidence and host/client test result.

The CLI returns JSON and is the default for every host. No MCP is started or globally registered. The optional adapter retains its original eight tools and two guide resources only when explicitly launched for an RoR2 task; use CLI for `symbols`/`bump`/`updates`. Setup uses the official SDK; never recreate MCP framing or replace ILSpy with guessed signature parsing.

## Evidence and versions

On 2026-10-27 the inspected Steam install was build `25921972`, Unity `2021.3.45f2`. These are observations, not defaults to impose on another machine. Current reference pins were selected against that installation; rerun discovery after game updates. Older boilerplates still reference Unity `2021.3.33`, older GameLibs/MMHOOK packages and floating dependencies. Do not copy their pins or preview language choices blindly.

`netstandard2.1` is the plugin target. A modern .NET SDK compiles it; the game still executes the Mono/BepInEx 5 plugin. BepInEx 6/IL2CPP templates are a different target. Publicized/stripped NuGet game references are compile-time inputs: they do not make private members accessible in the actual game. Use supported events, verified hooks, reflection/access tooling only when deliberately needed, and verify runtime access.

## Completion and recovery

Keep each mod's changelog and state current. Separate evidence into restore/build, package validation, loader startup, gameplay, multiplayer and save compatibility. An absent exception in a short log tail proves only that inspected tail. After a new load crash, restore the last working package and isolate the smallest change. Do not keep piling patches onto a failed baseline.

No API keys are needed for the normal workflow. External paid APIs and Unity editor bridges are optional, task-specific additions; confirm their host/authentication and actual callable capability before claiming they work. Never include game DLLs, decompiled source, caches, credentials or personal profiles in a distributed mod.

## Primary sources

- [R2Wiki](https://risk-of-thunder.github.io/R2Wiki/) and [assembly references](https://risk-of-thunder.github.io/R2Wiki/Mod-Creation/C%23-Programming/Assembly-References/).
- [Current Unity version](https://risk-of-thunder.github.io/R2Wiki/Mod-Creation/Unity-Version/) and [1.5.0 API migration](https://risk-of-thunder.github.io/R2Wiki/Mod-Creation/Updating-Your-Mods/Updating-Core-API-Changelog-1.5.0/).
- [R2API source](https://github.com/risk-of-thunder/R2API), [BepInEx 5 documentation](https://docs.bepinex.dev/v5.4.21/), [ILSpy](https://github.com/icsharpcode/ILSpy).
- [Thunderstore package requirements](https://wiki.thunderstore.io/mods/creating-a-package) and [official TCLI](https://github.com/thunderstore-io/thunderstore-cli).
