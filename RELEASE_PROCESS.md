# Release process

Authoritative steps for cutting a Forge release. Anywhere this file and a chat log disagree, this file wins.

## 1. Version the change

- `VERSION` and `ror2forge/__version__` carry the same MAJOR.MINOR.PATCH string.
- `CHANGELOG.md` gets a matching `# X.Y.Z — title (date)` heading at the top.
- Patch = corrective change to validation, packaging or docs. Minor = new CLI command, new template, new audit
  rule that can block a project. Major = a change that breaks existing project layouts or CLI flags.
- Run `.venv/Scripts/python.exe forge.py release-check --mode prerelease`. It must report `valid: true` and
  `tag_status` of `ok` or `not_required`.

## 2. Test

```
.venv/Scripts/python.exe -m unittest discover -s tests -v
.venv/Scripts/python.exe scripts/ci_smoke.py
```

`ci_smoke` builds, locked/offline-rebuilds, packages, bumps, rebuilds and repackages both templates. It is the
only local check that exercises the real compiler; unit tests alone do not prove a template still builds.

## 3. Land it

Main is protected: push a branch, open a PR, wait for all four checks (Windows tests and mod builds, CodeQL
actions/csharp/python), then squash-merge. Re-check CI on the merge commit SHA, not on the PR head.

## 4. Tag and publish

```
git tag -a vX.Y.Z -m "X.Y.Z — title" <merge-sha>
git push origin vX.Y.Z
```

Then build the source kit **twice** and confirm identical hashes:

```
git archive --format=zip --prefix=Risk-of-Rain-2-Forge-X.Y.Z/ <sha> -o artifacts/release-X.Y.Z/Risk-of-Rain-2-Forge-X.Y.Z-source.zip
```

Write `BUILD-RECEIPT.json` (`commit` = full `git rev-parse <sha>`, artifact sha256/size, CI conclusions) and
`SHA256SUMS` over the zip and the receipt. Publish with `gh release create`. After publishing, download the
assets back and compare hashes; a release is not verified until the published bytes match the receipt.

## 5. Verify a release you did not cut

```
.venv/Scripts/python.exe forge.py release-check --mode release --assets <downloaded-folder>
```

Release mode requires a single-`v` tag on HEAD, matching VERSION/package/changelog, and — with `--assets` — the
published files themselves. The archive must be a real ZIP named `Risk-of-Rain-2-Forge-<version>-source.zip`; the
receipt must be an object with `commit`, `artifact{file,sha256,size_bytes,files}` and a non-empty `ci_checks` list;
checksums must be well formed, unique, inside the folder, and match bytes and sizes: every `SHA256SUMS` entry must be well formed, unique, inside the folder, and match the
file's bytes and the receipt's claimed artifact hash/size, with the receipt commit equal to HEAD. It reports
`checks.version`, `checks.tag`, `checks.assets` and `release_verified` separately; a missing asset folder is
`not release-verified`, never a pass. ### Building the source archive

```bash
git -c core.autocrlf=false -c core.eol=lf archive --format=zip --prefix=Risk-of-Rain-2-Forge-<version>/ <tag>     -o artifacts/release-<version>/Risk-of-Rain-2-Forge-<version>-source.zip
```

Both overrides are required: `core.autocrlf=false` and `core.eol=lf`. without them `text=auto` files are exported with the checkout's native line endings (CRLF on Windows) while the
committed blob keeps LF, and `release-check` compares every member's Git blob hash to the tagged tree and correctly
reports every text file as changed. Archives published before 1.13.9 were built without the `core.eol` override and
therefore fail the content comparison; that is a true statement about those files, not a regression.

`checks.ci` is read independently from the repository's check-runs for the exact commit; nothing in the receipt is
trusted for CI. `release_verified` requires it to be `verified`. CI runs prerelease mode on every push; the tag
workflow runs release mode; `release-published.yml` re-verifies the downloaded bytes after publication.

## Compatibility statement

Keep three states separate in every release note:

- **compile-tested** — a template built with the pinned toolchain.
- **package-tested** — the ZIP validates and its bytes are reproducible.
- **in-game tested** — Risk of Rain 2 was launched with the mod and the log inspected.

The Forge never performs the third one; do not imply it does.

## Regenerating the R2API ownership table

```
.venv/Scripts/python.exe scripts/refresh_r2api_ownership.py
```

It derives modules and `<Type>API` owners from the upstream repository tree and records source, ref and date in
`ror2forge/r2api_ownership.json`. Review the diff before committing: a new module can change which projects the
audit blocks.

## Updating dependency pins

Pins live in `templates/*/` (csproj `PackageReference`), `NuGet.Config`, `forge.json` toolchain entries and the
Thunderstore dependency list in each template's `manifest.json`. `forge updates` reports what it tracks; it does
not edit pins, and latest is not the same as compatible. After any pin change: run the full suite, run
`ci_smoke`, and only then re-package. Never accept an update because the number is higher.
