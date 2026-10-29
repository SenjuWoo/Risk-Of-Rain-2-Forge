# Risk of Rain 2 Forge — WIP

[![CI](https://github.com/SenjuWoo/Risk-Of-Rain-2-Forge/actions/workflows/ci.yml/badge.svg)](https://github.com/SenjuWoo/Risk-Of-Rain-2-Forge/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Status: WIP](https://img.shields.io/badge/status-work%20in%20progress-orange)](docs/ROADMAP.md)

**Work in progress.** The CLI/build/package pipeline is tested; generated mods still need in-game validation. Windows x64 is the supported development platform. Unity asset authoring is a documented optional route, not a certified editor integration.

A local, CLI-first workbench for AI agents making Risk of Rain 2 mods. It supplies verified tooling, pinned templates, exact assembly inspection, build/package checks and a focused modding playbook. It works without an always-on service, account, API key or Unity editor for code mods.

Point an agent at this folder and tell it: **“Read AGENTS.md and use this forge to make my Risk of Rain 2 mod.”** The CLI is the default. No MCP is globally registered or automatically launched.

## Start

Install [Python 3.11+](https://www.python.org/downloads/) and the [.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0). In PowerShell:

```powershell
git clone https://github.com/SenjuWoo/Risk-Of-Rain-2-Forge.git
cd Risk-Of-Rain-2-Forge
.\forge.cmd setup
.\forge.cmd doctor
.\forge.cmd new MyMod --author MyTeam --template plugin
.\forge.cmd build MyMod
.\forge.cmd build MyMod --locked
.\forge.cmd package MyMod
```

Use `--template stats` for a configurable movement speed example using R2API's stat event. Its default multiplier is 1.0. Source lives in `projects/MyMod/src/`; package metadata lives beside it. `artifacts/` receives the checked ZIP. Generated mods and caches are private and excluded from source tracking.

The repository ships the tool installer, templates, agent skill and source. Setup installs pinned ILSpy, Thunderstore CLI and the official MCP SDK locally, retaining caches for offline restoration. Third-party binaries, game files and private caches are not in Git. It reuses your Python and .NET SDK. After an online setup, `forge.cmd setup --offline` restores from retained caches on the same Python/OS/architecture. See [toolchain and provenance](docs/TOOLCHAIN.md) for pins and limits.

A Steam copy of Risk of Rain 2 is needed for installed-assembly inspection and game testing. Template compilation uses NuGet references and works without an installed game. Set `ROR2_GAME_DIR` when automatic Steam discovery cannot find it.

## Commands

| Command | Purpose |
|---|---|
| `doctor` | Read-only Steam/game/Unity/profile/tool discovery, including game assembly hash |
| `updates` | Query official package feeds on demand; report current pins, scoped candidates and lookup failures |
| `setup [--offline]` | Restore pinned tools into this workspace |
| `new NAME --author TEAM [--template plugin\|stats]` | Create an owned mod without replacing source |
| `build NAME [--locked] [--offline]` | Restore and compile, with source/DLL evidence and a build log |
| `symbols QUERY [--assembly DLL] [--limit 20]` | Find exact type names through ILSpy; bounded, case-insensitive output |
| `inspect TYPE [--assembly DLL] [--member ID]` | Decompile one exact type or member using ILSpy |
| `bump NAME patch\|minor\|major\|X.Y.Z` | Back up and update mod version fields together, then rebuild |
| `package NAME` | Validate build freshness and create a deterministic Thunderstore ZIP |
| `validate ZIP` | Check paths, metadata, icon integrity, CRC and forbidden game references |
| `logs [--path LOG] [--lines 250]` | Read a bounded log tail and identify triage candidates |
| `lookup NAMESPACE NAME [--version VERSION]` | Read live Thunderstore package metadata and dependencies |
| `guide [overview\|code\|content\|assets\|networking\|debugging]` | Read the focused agent playbook |

```powershell
.\forge.cmd symbols CharacterBody --limit 10
.\forge.cmd inspect RoR2.RoR2Application
.\forge.cmd inspect RoR2.RoR2Application --member 'M:RoR2.RoR2Application.Awake'
.\forge.cmd lookup RiskofThunder R2API_RecalculateStats --version 1.7.0
.\forge.cmd logs --path 'C:\path\to\BepInEx\LogOutput.log'
```

`symbols` searches classes, interfaces, structs, enums and delegates in the installed RoR2 DLL by default, or a specific DLL with `--assembly`. It hides compiler-generated helpers, ranks an exact match first and reports truncation, the total matches and assembly hash. Feed a returned name to `inspect`; no whole-game source dump or persistent index is needed.

To iterate on a generated mod:

```powershell
.\forge.cmd bump MyMod patch
.\forge.cmd build MyMod --locked --offline
.\forge.cmd package MyMod
```

`bump` checks that forge.json, manifest.json, the project Version and PluginVersion agree before editing them. It preserves original bytes under the mod's `build/version-backups/`, updates generated state/changelog notes and rolls back a failed write. Explicit versions must increase. Custom/ambiguous declarations are refused rather than guessed; the automated version preflight does not support source containing raw C# string delimiters. Existing ZIPs remain intact; the changed source requires a rebuild. Use an online build when references are not cached yet.

Normal output is JSON; errors use a nonzero exit. Invalid ZIPs return their JSON report on stdout with exit 1. `--debug` before the command adds a traceback on stderr. Build logs and receipts live in each mod's `build/` folder.

Run `forge.cmd updates` when refreshing the workbench or investigating a game/tool update. It checks metadata without installing anything or changing pins. Reference candidates stay scoped to the template's loader/Unity line; a newer game reference still needs compatibility verification. Failed lookups are reported as unknown and produce exit 1, rather than pretending everything is current. This command has no background schedule and adds no MCP tool.

`doctor` reports build readiness independently of game discovery: the templates can compile with a compatible SDK and NuGet references on a machine without RoR2. It reports the SDK selected from the forge root, its resolution error if any, and the separate installed-SDK inventory. A project's own global.json may select another SDK; its build remains authoritative. Default game inspection still needs the installed assembly. Setup's complete toolchain requires .NET 10 for ILSpy.

Discovery reads Steam's registry/library manifests and r2modman data. Override it with `ROR2_GAME_DIR` / `ROR2_MODMAN_DIR`, or a private `forge.local.json` containing `game_dir` / `modman_dir`. The manager directory is the **RiskOfRain2** directory containing `profiles/`. No profile is changed.

## Assets, content and multiplayer

The [recipes](docs/RECIPES.md) cover items/equipment, survivors/skins/stages, hooks, asset bundles, networking and debugging. Place produced runtime bundles/audio/etc. in a mod's `content/`; packaging preserves their paths below `plugins/NAME/`. Code, extra DLLs and nested archives are refused there. The ZIP includes the mod's own DLL, manifest, README, icon, optional project LICENSE and declared content, rather than the entire build folder.

Unity authoring is optional and needs a matching editor and verified EditorKit/ThunderKit setup. Unity itself is not bundled. Read [the asset route](docs/RECIPES.md#assets-and-unity) before creating an editor project. Runtime shader, gameplay, save and multiplayer checks require actual game sessions; compilation cannot settle them.

## Optional MCP, off by default

CLI use requires no MCP configuration. If a particular agent host benefits from typed tools/resources, explicitly start `mcp.ps1` for that task, or configure that host **only in its trusted RoR2 project**:

```json
{
  "command": "<absolute forge path>/.venv/Scripts/python.exe",
  "args": ["-m", "ror2forge.mcp_server"],
  "cwd": "<absolute forge path>"
}
```

This is a server entry example, not a provider-specific full config. Nothing here installs it into personal/global settings. Eight typed tools and two guide resources expose the original workflow. New `symbols`, `bump` and `updates` operations use the CLI, keeping this optional schema small. A host must start the server before tools are callable; stop it when the RoR2 task ends. [The agent guide](docs/AGENT_GUIDE.md) and [reusable skill](skills/ror2-forge/SKILL.md) work with CLI-only agents too.

## Validation and boundaries

Run `.venv\Scripts\python.exe -m unittest discover -s tests -v` after setup. MCP tests use a real local SDK client/server connection. CI also restores/builds both templates, repeats locked offline builds and checks deterministic ZIPs on a clean Windows runner without a game install. [VALIDATION.md](VALIDATION.md) distinguishes development-machine evidence from public CI. Generated examples and evidence files are local outputs, not files shipped in a clone.

See [CONTRIBUTING.md](CONTRIBUTING.md), [the roadmap](docs/ROADMAP.md), [the changelog](CHANGELOG.md) and [security reporting](SECURITY.md). This WIP source publication has no stable binary release.

New packages are local candidates. The forge never installs into an active profile or uploads to Thunderstore. It refuses stale builds and different bytes under an existing artifact version; bump all version fields to create a changed release. Arbitrary custom MSBuild scripts/imports can execute code: build trusted owned source and record external inputs explicitly.

Original forge code is MIT; bundled third-party tools retain their own terms. Local installation does not establish permission to redistribute every tool; see [THIRD_PARTY.md](THIRD_PARTY.md).
