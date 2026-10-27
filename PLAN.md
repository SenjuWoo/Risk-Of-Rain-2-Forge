# Risk of Rain 2 Forge 1.0.0

Build a local/private, agent-first modding workbench. Use a dependency-free Python CLI and the official MCP SDK adapter; use .NET/NuGet and ILSpy rather than reinventing compilers or decompilers. No game, saves, mod-manager profiles, personal agent config, or remote publication is modified.

1. Inspect installed game/profiles and primary upstream metadata. Establish ownership.
2. Pin and install local ILSpy, Thunderstore CLI, MCP SDK; preserve provenance and offline caches.
3. Implement JSON discovery, scaffolding, build, assembly inspection, package validation/creation, package lookup, and log triage. All generated mods live under projects/.
4. Provide agent instructions, evidence-based recipes for code/content/assets/networking, MCP setup examples, and recovery docs.
5. Test trust boundaries and failures; scaffold/build/package real mods; test MCP initialize/list/call and selective decompilation.

Completion means passing automated tests plus real restore/build/package and tool/MCP smoke tests. Compile/package evidence is separate from game runtime evidence.

Status: all five steps completed locally. See STATE.md and VALIDATION.md for 33 passing tests, actual locked/offline builds, package hashes, optional MCP proof and exact runtime/editor gaps. User clarified CLI preference; no MCP is auto-started or globally registered.

Scope reaches CLI/parser, core operations, two templates, dependency pins, local tools, MCP adapter, tests, launchers, docs and state. No existing callers/data exist. Main risks are stale game APIs, package drift, accidental profile writes, and redistribution of game assemblies; lock versions, enforce owned output paths and package an allowlisted payload.
