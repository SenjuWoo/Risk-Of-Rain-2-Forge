# Toolchain and recovery

Verified on 2026-10-27 against local Steam build 25921972, Unity 2021.3.45f2. Discovery is read-only; these observations are not promises about a future game patch.

| Component | Pin | Role |
|---|---|---|
| Python | Existing 3.14.10 here; CLI needs 3.11+ | Dependency-free CLI and local MCP environment |
| .NET SDK | Existing 10.0.403 here; setup needs 10+ | netstandard2.1 compiler and official tools |
| ILSpy / ilspycmd | 11.2.0.10050 | Exact type/member decompilation |
| Thunderstore CLI / tcli | 0.2.4 | Official optional advanced packaging/publishing tooling; forge never invokes upload |
| MCP Python SDK | 2.3.0 | Optional stdio adapter; never loaded by CLI-only operations |
| BepInEx.Core | 5.4.21 | BepInEx 5 compile reference |
| RiskOfRain2.GameLibs | 1.5.0-r.1 | Publicized/stripped compile references |
| UnityEngine.Modules | 2021.3.45 | Compile references matching observed runtime family |
| R2API.RecalculateStats | 1.7.0, stats template only | Stat event; transitive GameLibs/MMHOOK versions recorded by NuGet lock |

NuGet sources are nuget.org and the BepInEx feed (`https://nuget.bepinex.dev/v3/index.json`). References are exact ranges; transitive resolutions live in each mod's `src/packages.lock.json`. Do not replace these with floating versions. Use only the R2API modules a mod needs. Pinned runtime package IDs are in each mod's manifest; the two package/version namespaces are different.

`tools/toolchain-receipt.json` records source URLs, versions, installed paths, smoke results and downloaded SHA256 digests. `tools/cache/python-requirements.lock` pins all Python wheels by version/hash. `tools/cache/wheels` and `tools/cache/nuget` retain the setup payload. Reference packages restore into `tools/cache/packages`; caches never become runtime ZIP content.

The hashes record bytes received over HTTPS from official package feeds; they are not an independently published vendor signature. NuGet/PyPI license metadata and the retained package license files remain authoritative. No personal NuGet sources, keys or provider configurations are copied into the forge.

`forge setup` is idempotent and detects conflicting local tool versions. It reuses the shared Python and .NET; no second interpreter, global tool, editor bridge, service or machine-wide MCP registration is installed. The launcher avoids this machine's inaccessible WindowsApps Python alias by probing a real executable. Dotnet cache/home/temp locations are scoped locally, telemetry/certificate generation are disabled for setup/build subprocesses. An initial direct dotnet provisioning command created an untrusted ASP.NET development certificate before that prevention was added; it was not trusted or used by the forge.

Offline setup has been tested from a fresh isolated root using the retained tool archives/wheels. Those caches match this Windows x64/Python build; another platform needs its own initial online setup. Offline mod builds require references to have been restored previously; template defaults are cached here. An added package needs one online restore before it can build offline.

The stats template's transitive MMHOOK.RoR2 2026.10.8 package declares a .NET Framework asset, so NuGet reports NU1701 when referenced by netstandard2.1. The build succeeds; warnings remain visible in build logs/JSON receipts. This is not silently suppressed and runtime compatibility still needs a game session.

After game/tool updates: run doctor, inspect relevant changed APIs, resolve and deliberately update exact pins, restore a lock, build, package, then repeat runtime testing. Never replace a known-good release artifact with different bytes. Preserve old receipts/packages for rollback. Delete/reinstall only owned tool outputs if repair is needed; keep projects, lock files and artifacts.
