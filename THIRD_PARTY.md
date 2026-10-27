# Third-party components

The forge's original source is covered by LICENSE. No claim is made to own or relicense third-party code, game assemblies or tool binaries.

- ILSpy/ilspycmd: [icsharpcode/ILSpy](https://github.com/icsharpcode/ILSpy), MIT and the dependency terms in its NuGet package.
- MCP Python SDK: [modelcontextprotocol/python-sdk](https://github.com/modelcontextprotocol/python-sdk), MIT; retained wheels contain dependency metadata/licenses.
- Thunderstore CLI: [thunderstore-io/thunderstore-cli](https://github.com/thunderstore-io/thunderstore-cli). NuGet 0.2.4 declares no license; upstream license endpoint was unavailable during verification. This is a local/private installed tool. Public redistribution permission is unverified; do not include its binaries in a public forge release without resolving that.
- BepInEx/R2API/Unity/GameLibs/MMHOOK: compile/runtime dependencies retain their upstream terms. NuGet archives and game DLLs are private reference inputs. Generated mod packages exclude reference assemblies and do not bundle the loader/R2API.
- The generated placeholder icon is original procedural artwork. Replace it and document asset credits before publishing a mod.

Exact downloaded package identities/hashes and declared NuGet tool license metadata are in tools/toolchain-receipt.json. Shared Python/.NET and optional Unity installations are not redistributed by this source kit.
