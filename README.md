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
| `setup [--offline]` | Restore pinned tools into this workspace |
| `new NAME --author TEAM [--template plugin\|stats]` | Create an owned mod without replacing source |
| `build NAME [--locked] [--offline]` | Restore and compile, with source/DLL evidence and a build log |
| `inspect TYPE [--assembly DLL] [--member ID]` | Decompile one exact type or member using ILSpy |
| `package NAME` | Validate build freshness and create a deterministic Thunderstore ZIP |
| `validate ZIP` | Check paths, metadata, icon integrity, CRC and forbidden game references |
| `logs [--path LOG] [--lines 250]` | Read a bounded log tail and identify triage candidates |
| `lookup NAMESPACE NAME [--version VERSION]` | Read live Thunderstore package metadata and dependencies |
| `guide [overview\|code\|content\|assets\|networking\|debugging]` | Read the focused agent playbook |

```powershell
.\forge.cmd inspect RoR2.RoR2Application
.\forge.cmd inspect RoR2.RoR2Application --member 'M:RoR2.RoR2Application.Awake'
.\forge.cmd lookup RiskofThunder R2API_RecalculateStats --version 1.7.0
.\forge.cmd logs --path 'C:\path\to\BepInEx\LogOutput.log'
```

Normal output is JSON; errors use a nonzero exit. Invalid ZIPs return their JSON report on stdout with exit 1. `--debug` before the command adds a traceback on stderr. Build logs and receipts live in each mod's `build/` folder.

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

This is a server entry example, not a provider-specific full config. Nothing here installs it into personal/global settings. Eight typed tools and two guide resources mirror the CLI. A host must start the server before tools are callable; stop it when the RoR2 task ends. [The agent guide](docs/AGENT_GUIDE.md) and [reusable skill](skills/ror2-forge/SKILL.md) work with CLI-only agents too.

## Validation and boundaries

Run `.venv\Scripts\python.exe -m unittest discover -s tests -v` after setup. MCP tests use a real local SDK client/server connection. CI also restores/builds both templates, repeats locked offline builds and checks deterministic ZIPs on a clean Windows runner without a game install. [VALIDATION.md](VALIDATION.md) distinguishes development-machine evidence from public CI. Generated examples and evidence files are local outputs, not files shipped in a clone.

See [CONTRIBUTING.md](CONTRIBUTING.md), [the roadmap](docs/ROADMAP.md), [the changelog](CHANGELOG.md) and [security reporting](SECURITY.md). This WIP source publication has no stable binary release.

New packages are local candidates. The forge never installs into an active profile or uploads to Thunderstore. It refuses stale builds and different bytes under an existing artifact version; bump all version fields to create a changed release. Arbitrary custom MSBuild scripts/imports can execute code: build trusted owned source and record external inputs explicitly.

Original forge code is MIT; bundled third-party tools retain their own terms. Local installation does not establish permission to redistribute every tool; see [THIRD_PARTY.md](THIRD_PARTY.md).
