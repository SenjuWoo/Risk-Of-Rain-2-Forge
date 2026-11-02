# Workspace ownership

- Project root: `.` (this file's directory; one owner shared by every agent).
- Active source: `.`; original forge modules in ror2forge/, templates/, docs/, tests/ and launchers. Version 1.8.0 WIP in VERSION; protected main is updated through verified pull requests.
- Versioning: semantic versions in VERSION/CHANGELOG.md; source remains in this root. Preserve known-good artifacts and receipts rather than duplicating source snapshots.
- Repository: SenjuWoo/Risk-Of-Rain-2-Forge, public MIT WIP source; explicitly authorized by user on 2026-10-27.
- Publication intent: public source and initial WIP source-kit prerelease explicitly authorized on 2026-10-29. Release v1.2.0 retains external tool setup; no stable binary release is requested. Keep generated mods, game files, tool binaries/caches and private evidence local.
- Explicit GitHub publication: public and MIT for original work by default, subject to rights/platform terms; preserve existing licences. Generic publication uses the appropriate destination (Nexus for Skyrim); do not create duplicate source hosting for mods needing no compilation.
- Existing-repository maintenance: preserve its remote/visibility and follow the requested update, documentation, push and release scope.
- Read-only inputs: installed products, game Data/staging/saves and supplied references.
- Outputs: tools/ and .venv/ are local installed dependencies/caches; projects/ owns generated mods; artifacts/ owns ZIPs and validation evidence. None is a live game/profile directory.
- Release staging: mod packages include only explicit runtime payload and required licenses. No source paperwork/logs/reference DLLs. Forge source includes its actual tools setup/tests/help; public binary redistribution needs separate licensing review.
- Recovery: read STATE.md and version/build/run metadata before continuing; keep the last known-good artifact.


Read the existing evidence and update the active-source/version fields before substantive edits. Do not create another owner or move files merely to match a template.
