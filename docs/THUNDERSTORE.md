# Thunderstore page and dependency pins

Checked against the package wiki and the live package API on 2026-11-01, then used to pack a survivor without uploading it. `forge validate` already enforces the zip rules below. This page is the part the validator cannot see: what the site does with the zip after you upload it.

Sources: [Creating a package](https://wiki.thunderstore.io/mods/creating-a-package), [Updating a package](https://wiki.thunderstore.io/mods/updating-a-package), [Packaging your mods](https://wiki.thunderstore.io/mods/packaging-your-mods), [Global rules](https://wiki.thunderstore.io/moderation/global-rules).

## The zip

The root must contain `icon.png` (exactly 256×256 PNG), `README.md` and `manifest.json`. `CHANGELOG.md` is optional and is the changelog tab. Names are case-sensitive. Do not zip a parent folder.

`manifest.json` fields that matter:

| Field | Rule |
|---|---|
| `name` | Letters, digits, underscore, max 128. Permanent. A rename is a new package. Underscores display as spaces. |
| `version_number` | `Major.Minor.Patch`. An uploaded version cannot be edited. A higher number is the only update. |
| `description` | The card blurb. 1–250 characters. No version number; the version field owns that. |
| `website_url` | Required key. `""` is valid. |
| `dependencies` | `Team-Package-Version` strings. Each is a **minimum**. The manager installs that version or newer, and the highest minimum in the whole graph wins. |

Runtime files go under `plugins/`, `patchers/`, `config/`, `core` or `monomod` (optionally under `BepInEx/`). Any other top-level folder is emptied into the package root on install. `forge validate` rejects that layout.

The README inside the zip is the package page for that version. Relative images in the zip are not the gallery. Gallery frames are a separate upload on the package page. The README of a survivor should say how to install, that every player including the host needs the mod, how to select the survivor, and the skill numbers the code actually deals. Put the version in the manifest and the changelog, not in the README body.

## The upload form

Categories are chosen on the form, not in the manifest. A custom survivor is a mod for everyone in the lobby. Do not mark it client-side.

The Risk of Rain 2 community has an `AI Generated` category. The global rules (updated 2026-10-28) say a package with AI-generated assets or code should get that category where the community has it, and that this is generally not enforced for the README or the icon. Tick the category on the form. Do not put a model name, an "authored by" line, or a vendor credit in the package.

NSFW stays off unless the mod is NSFW. The team in the URL is chosen at first upload and is not the folder name you used locally.

A new package can take up to about 35 minutes to show in the mod manager. The site link works sooner. To test before that, import the zip as a local mod. Local mods do not pull dependencies or receive updates.

## Pins that were live on 2026-11-01

These package versions returned active metadata. They are observations, not a reason to bump a working mod.

| Package | What it declared |
|---|---|
| `RiskofThunder-R2API_Core-5.3.0` | depends on `bbepis-BepInExPack-5.4.2120` and `RiskofThunder-HookGenPatcher-1.2.9` |
| `RiskofThunder-R2API_ContentManagement-1.1.0`, `R2API_Skins-1.4.14`, `R2API_RecalculateStats-1.7.0` | depend on Core 5.3.0, HookGenPatcher 1.2.3, and `bbepis-BepInExPack-5.4.2109` |
| `RiskofThunder-R2API_Language-1.1.0` | depends on Core 5.2.0 |
| `RiskofThunder-R2API_Prefab-1.1.1` | depends on older Core and ContentManagement minimums |
| `bbepis-BepInExPack-5.4.2109` and `5.4.2120` | both active. The package page's newest build that day was 5.4.2122. |
| `RiskofThunder-RoR2BepInExPack-1.49.0` | active, and it declares **no** dependencies. It is not pulled in by Core. |

A manifest that lists `bbepis-BepInExPack-5.4.2109` plus Core 5.3.0 still installs BepInExPack 5.4.2120 or newer, because Core's minimum is higher. Do not change a pin to the page's "latest" unless you compiled and ran against that build.

HookGenPatcher is already required by the R2API modules. Listing it yourself is optional.

`RoR2BepInExPack` is the scaffold's chosen extra pack: `forge new` still depends on `RiskofThunder-RoR2BepInExPack-1.49.0` and `bbepis-BepInExPack-5.4.2122`. Leave those template pins alone. A plugin that does not reference `RoR2BepInExPack.dll` can omit it. The played survivor's DLL did not reference that assembly, it was not in the manifest, and the plugin loaded. Do not add the pack only because a dev profile happens to contain it, and do not delete it from the template without a new measurement.

`forge audit` remains the check that every `using R2API.<Module>` and every `com.bepis.r2api.*` dependency attribute has a matching manifest line. A missing line is how a plugin never loads for anyone except the author.
