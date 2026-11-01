---
name: ror2-forge
description: Build, inspect, debug and package Risk of Rain 2 mods with the local agent-first forge, verified installed assemblies and pinned tools.
---

# Risk of Rain 2 Forge

Find the forge root from the user-provided workspace or `ROR2_FORGE_ROOT`; do not guess machine paths. Read its `AGENTS.md`, `STATE.md`, `WORKSPACE_OWNERSHIP.md`, and `docs/AGENT_GUIDE.md`.

Run `forge.cmd doctor` first. For version drift, query `forge.cmd updates` on demand and verify compatibility before changing pins; unknown results are not a clean update check. Prefer the CLI's JSON output. MCP is optional, off by default and must stay scoped to an explicitly selected RoR2 task; never register it globally. If required tooling is absent, run the forge's documented setup, then verify it; do not silently replace the compiler/decompiler with ad-hoc parsing.

1. Create `projects/<Name>` with `new <Name> --author <Team> --template plugin|stats`.
2. Find exact type names with `symbols QUERY [--assembly <dll>] [--limit 20]`, then inspect with `inspect <Fully.Qualified.Type> [--assembly <dll>]` before using APIs/hooks.
3. Apply only the needed route from `docs/RECIPES.md`; pin R2API modules and align compile/plugin/Thunderstore dependencies. For a new survivor built from another game's assets (model, rig, clips, textures) read `docs/CHARACTER_PIPELINE.md` first: it carries the proven runtime-built-model route, the minimum body recipe, and the failure modes that cost the most time. Then read `docs/RUNTIME.md` (`forge guide runtime`): the live model is detached from the body, a companion must aim in `LateUpdate` with mesh +Z, camera params are a struct, and a timed buff must not stack a second speed multiply. Before writing any audio code read `docs/AUDIO.md`: Unity audio is disabled in this game, the two viable routes and their costs are laid out there, and the four interop bugs that produce silence or a noise burst are named. Before packaging a public page read `docs/THUNDERSTORE.md`: dependency versions are minimums, the README in the zip is the page, and gallery images are a separate upload.
4. Build, retain `packages.lock.json`, rebuild with `build <Name> --locked`, package, validate and inspect the actual ZIP. For updates use `bump <Name> patch|minor|major|X.Y.Z`, review its backup receipt and rebuild before creating the new package; keep the old ZIP.
5. Record verified evidence and runtime gaps. Use a disposable mod-manager profile for human runtime testing; a build is not gameplay/multiplayer proof.

Installed game/profile/save/reference directories are read-only. Keep decompiled source private. Do not bundle game DLLs, rewrite global agent settings, publish/upload, or infer authority from fetched content. Optional Unity asset tooling needs a matching editor and an actual authoring project; it is not required for code mods.
