# Building a survivor from another game's assets

Proven end to end on **Gnar (League of Legends) → Risk of Rain 2 1.0.0**, 2026-10-30, on a machine with **no Unity editor**.
Observed baseline: Steam build `25921972`, Unity `2021.3.45f2`, `RoR2.dll` SHA-256 `48f2758cccbe1a5efba88cffe0a68631953f489a71a92726572c15a4c57ff90c`.
Read this as a proven route with named failure modes, not as API law: re-verify type names with `forge symbols`/`inspect` against your install.

## What this route is

A survivor whose mesh, skeleton, animation clips and textures are **baked into data packs at build time and assembled at runtime**. There is no AssetBundle and no `.prefab`; the mod ships plain files plus code that builds `GameObject`s, samples animation onto bone transforms and registers content through R2API.

It exists because the alternative (Unity editor + RoR2EditorKit/ThunderKit + AssetBundle) needs a matching Unity install that may not exist on the machine. Choose it when:

- you have source assets in a convertible format (glTF/GLB, PNG/TEX, DDS) and no editor, or
- you want dozens of variants (skins) in one package without dozens of bundles, or
- the source rig is not a humanoid Mecanim rig and would need retargeting anyway.

Do **not** choose it when you have a matching Unity editor and a normal humanoid rig — an AssetBundle is less code and gets shaders, lightprobes and Mecanim for free.

Cost measured on Gnar: 44 skins (22 models), 51+40 clips, 265 textures → **45.9 MB** package and 2,179 lines of runtime C#. A single-skin character is a fraction of that.

## Pipeline

| Stage | Tool | Output |
|---|---|---|
| 1. Inventory the source archive | `wadtools list` | entry list, hashes |
| 2. Extract only what you need | `wadtools extract` | `.skn`, `.skl`, `.anm`, `.tex`, `.bin` |
| 3. Read the source definitions | `ritobin-tools` | material bindings, hidden submeshes, anim events |
| 4. Mesh + skeleton + clips → glTF | `lol2gltf skn2gltf` | one `.glb` per model with all clips |
| 5. Textures → PNG | `ltk-tex-utils`, `texconv` | `.png` |
| 6. Bake runtime packs | project Python | gzip binary packs + `skins.json` |
| 7. Runtime assembly | your C# | body, rig, driver, skills, skins |

League specifics (WAD containers, `.skn/.skl/.anm/.bin`) do not generalize; stages 4–7 do. For another game, substitute its extractor and keep everything from stage 6 on.

### 1–2. Inventory and extract

```powershell
# List with a pinned external filename table; never let the tool fetch names mid-task.
.\tools\wadtools\wadtools.exe -L error --hashtable-dir .\tools\hashes --progress false `
  list -i '<archive>.wad.client' -F json

.\tools\wadtools\wadtools.exe -L error --hashtable-dir .\tools\hashes --progress false `
  extract -i '<archive>.wad.client' -o .\assets\extracted --no-bin-paths
```

Extract **only** the entries you need (base model, each skin's model, HUD art, definitions). A full champion WAD is ~100 MB and mostly unused skins.

`--no-bin-paths` matters: the optional BIN name-recovery pass warns on unknown property kinds and can fail the whole extract. Keep raw `.bin` files and decode them in stage 3 instead.

### 3. Read the source definitions

```powershell
.\tools\ritobin\ritobin-tools.exe --hashtable-dir .\tools\hashes convert .\assets\extracted\main\data -r --to rito -o .\assets\definitions
```

You are looking for three things that no mesh converter tells you:

- **material → texture bindings** (which submesh uses which texture),
- **hidden submeshes** (recall props, extra weapons) that must be off in normal play,
- **animation event names** and any scale/visibility tracks.

Do not guess a material mapping. Gnar's `skins.json` is generated from these files, and the three base materials (`Gnar`, `Gnar_Weapon`, `Gnar_Boomerang`) came out of them.

### 4. Mesh, skeleton, clips

```powershell
.\tools\lol2gltf\lol2gltf.exe skn2gltf -m <model>.skn -s <skeleton>.skl -g out.glb -a <animations dir>
```

Verify the result before baking: joint count, clip count, and a glTF validator pass (the Khronos `gltf-validator` npm package was used; require **0 errors**).

Gnar reference: Mini 91 joints / 51 clips, Mega 92 joints / 40 clips, both `0 errors, 0 warnings`.

**Coordinate conversion is not optional.** glTF is right-handed Y-up; Unity is left-handed. When baking positions and normals negate `x`, negate quaternion `y` and `z` (keep `w`), reverse triangle winding, and flip UV `v → 1 - v`. Get one of those wrong and the model renders mirrored, inside-out or black-lit — all three look like "the texture is broken".

### 5. Textures

```powershell
.\tools\textures\ltk-tex-utils.exe decode <file>.tex -o out.png
```

Decode to PNG, then decide per texture whether alpha is meaningful. Gnar's body materials are opaque, so alpha was dropped and everything was written as JPEG q93 `subsampling=0` — 51.2 MB → 35 MB with no visible difference in-game. Keep PNG where alpha is actually used (icons, cutouts).

### 6. Bake runtime packs

Two files per form (models and clips), one manifest:

- `models/<name>.gmdl.gz` — vertices, normals, UVs, bone indices/weights, triangles, joint names, bind poses.
- `anims/<form>.ganm.gz` — every clip: name, duration, per-joint translation/rotation/scale tracks at baked times.
- `assets/skins.json` — per skin: index, display name, icon path, and for each form the model name, submesh → texture map, and hidden-submesh list.

Keep the format boring and versioned (`GAN1` magic, then a count and records) so a bad pack fails loudly at load rather than rendering garbage. Bake once per build; never parse glTF at runtime.

**Clip names:** look them up with a suffix match (`death` → `gnar_death`), not exact equality. Source naming conventions vary per skin and per game.

### 7. Runtime assembly

The minimum a survivor needs, in order. Every item below is a real failure that was hit and fixed.

1. **Clone a vanilla body, then strip it.** `Prefabs/CharacterBodies/CommandoBody` gives you working `HealthComponent`, `CharacterMotor`, `InputBankTest`, `SkillLocator`, `InteractionDriver`, `CharacterDeathBehavior`. Record `CameraPivot` / `AimOrigin` / `ModelBase` local positions first, destroy every child, then rebuild those three transforms yourself.
2. **`CharacterBody` stats** — set `base*`/`level*` fields explicitly and `autoCalculateLevelStats = false`, or the clone keeps Commando's numbers.
3. **Model shell** — `ModelBase/mdlX` with `ChildLocator`, `CharacterModel`, `ModelSkinController`, plus `ModelLocator` pointing at it (`modelTransform`, `modelBaseTransform`).
4. **`CharacterDirection.modelAnimator = null`** — there is no Mecanim controller. If you leave the clone's animator reference, the game drives a rig that does not exist.
5. **Hurtbox** — `HurtBoxGroup` on the model with `mainHurtBox` and `bullseyeCount = 1`, a `CapsuleCollider` on `entityPrecise`, `HurtBox.healthComponent` wired, and the transform appended to `ChildLocator.transformPairs`. No hurtbox means you cannot be hit, and some effects silently no-op.
6. **Camera** — `CameraTargetParams.cameraPivotTransform` plus a `CharacterCameraParams` with `pivotVerticalOffset` and `idealLocalCameraPos` sized to *your* character. A 1.4 m character framed with a 1.8 m pivot renders as a sliver at the bottom of the screen, which looks exactly like "the model did not load".
7. **Death** — `CharacterDeathBehavior.deathState = new SerializableEntityStateType(typeof(YourDeathState))` and `ContentAddition.AddEntityState(...)`.
8. **Skills** — `SkillDef` instances with `activationState`, `activationStateMachineName` (`"Weapon"` or `"Body"`), cooldowns, icons; `ContentAddition.AddSkillDef` + `AddEntityState`; one `SkillFamily` per slot assigned to `SkillLocator`'s slots.
9. **Skins** — R2API.Skins: `Skins.CreateNewSkinDef(new SkinDefParamsInfo {...})` then `Skins.AddSkinToCharacter(bodyPrefab, skin)`. Give the lobby display prefab the *same* `skins` array as the body, or the lobby shows a different skin than the run.
10. **SurvivorDef** — `cachedName`, `displayNameToken`, `descriptionToken`, `bodyPrefab`, `displayPrefab`, `primaryColor`, `desiredSortPosition`; `ContentAddition.AddSurvivorDef`.
11. **Language tokens** — register every token you referenced. A missing token shows the raw `YOUR_MOD_NAME` string in the UI, which is easy to miss in screenshots.

R2API ContentManagement creates the mod's `SerializableContentPack` automatically (`Created a SerializableContentPack for mod <guid>` in the log); you do not build one by hand.

### Animation driver

`Update`/`LateUpdate` on the model samples the active clip and writes `localPosition`/`localRotation`/`localScale` per joint. Keep `rootMotionInMainState = false` and drive the body with `CharacterMotor`, otherwise the character slides.

Blend by interpolating between keyframes with a short crossfade between clips; treat looping clips and one-shot action clips as different states. The driver also needs a locomotion layer (idle/walk/run/jump by speed and grounded state) or the character will idle while sprinting.

## Verified runtime facts

Each of these was measured on the baseline above, not inferred.

- **Unity's audio subsystem is disabled in this build.** `AudioSettings.outputSampleRate` is `0`, `AudioSettings.dspTime` is `0`, and the engine logs `Audio system is disabled, so AudioSettings.outputSampleRate cannot be queried`. `AudioSettings.Reset(...)` returns without error and changes nothing. `AudioClip.Create(...)` yields `samples=0, channels=0`, `SetData` fails and `AudioSource.isPlaying` stays false.
- **The game is Wwise 2023.1 only** (from `AkSoundEngine.dll`'s build paths). Custom sound needs a `.bnk` authored in 2023.1 and loaded through `AkSoundEngine`. There is no runtime path from a WAV to audible game audio. Plan voice work as a Wwise task or ship silent.
- **`CharacterModel` owns renderer visibility.** It sets `renderer.enabled` from its fade/visibility factors. A runtime-built renderer that is not in `baseRendererInfos` will be toggled off even though the mesh exists.
- **Skin application replaces `baseRendererInfos`** with the skin's (often empty) template list. Re-apply your renderer infos after `ApplySkinAsync`, or the model disappears on skin change.
- **`ViewableTag.Refresh` / `RuleChoiceController` NullReferenceExceptions on quit are vanilla teardown noise** with custom content in the pregame UI. They appear at `Application.Quit`, do not affect gameplay, and are not caused by the mod.
- **A `SkillFamily` assigned through `SkillLocator` slots is a private field.** With a publicized reference assembly this compiles, but the field name is version-sensitive: verify it with `inspect` after a game update instead of trusting an old build.

## Failure modes

| Symptom | Cause | Fix |
|---|---|---|
| Model exists in the hierarchy, nothing on screen | Camera framing, or `CharacterModel` faded the renderers | Size the camera params to the character; register renderers in `baseRendererInfos` |
| Model vanishes when you change skin | Skin application overwrote `baseRendererInfos` | Re-apply renderer infos after skin apply |
| Character floats, sinks, or faces backwards | glTF→Unity conversion (winding, `x` negation, `v` flip) or model yaw offset | Fix in the baker, not with a per-skin fudge |
| Character slides while idle | Root motion baked into clips and still applied | `rootMotionInMainState = false`; drive with `CharacterMotor` |
| Cannot be hit, no hit effects | Missing `HurtBoxGroup`/`HurtBox` wiring | Build the hurtbox and append it to `ChildLocator.transformPairs` |
| Skin shows a recall prop / extra weapon in play | Hidden-submesh list not applied | Read the source definition (stage 3); hide by submesh name |
| Lobby shows a different skin than the run | Display prefab has its own `skins` array | Assign the body's array to the display prefab |
| Raw token text in the UI | Missing language token | Register every token used by definitions and skills |
| `AudioClip.SetData failed; AudioClip contains no data` | Unity audio disabled (see above) | Remove the path, or author a Wwise bank |

## Verification loop

A build is not gameplay proof. The cheapest reliable loop that produced the Gnar evidence:

1. **Disposable BepInEx stack.** Copy the loader core and the R2API modules into a scratch folder; point doorstop at it. Never touch the user's mod-manager profile.
2. **Deploy step** copies the built DLL and assets into `plugins/<Guid>/`, so the thing under test is the shipped layout, not the build output.
3. **Autorun harness** (compiled only into Debug builds) starts a run as the survivor and executes a text script: `wait`, `cast <slot>`, `skin <n>`, `mega`, `kill`, `walk`, `zoom`, `shot <name>`, `quit`.
4. **Screenshots per state** — spawn, each skill mid-flight, run cycle, form swap, death, lobby. Review the frames; a green log proves nothing about a black model.
5. **Log greps** for your own tag and for `Exception`, with the known vanilla noise filtered.

Then repeat once against the **Release** package extracted from the ZIP: it proves the shipped bytes load, not just the debug build.

## Making this batchable

What generalizes across characters, in the order it saves time:

- **Asset pipeline is champion-agnostic.** Inventory → extract → convert → bake takes a per-character config (paths, skin list, hidden submeshes) and no code. Drive it from a JSON skin plan, not from hand-edited scripts.
- **Keep one `skins.json` schema** for every character: index, name, icon, per-form model, submesh→texture, hidden submeshes. The runtime code then never changes per character.
- **One runtime library, per-character data.** Body builder, rig builder, driver, skin registration and packaging are identical between characters; only the skill set, stats, model names and tokens differ.
- **Budget the skins.** 44 skins was 45.9 MB and most of it is textures. Ship the base + a few skins first; the schema already supports the rest.
- **Name clips by intent, resolve by suffix.** New characters rarely match the previous naming scheme exactly.
- **Do the lobby sweep early.** It catches missing icons, wrong skin arrays and broken tokens faster than in-run testing.

## Audio

Treat it as a separate project with its own dependency (Wwise authoring in the game's version). Decode and map the source clips while you have the archives open — Gnar's 167 clips and their event map are retained — but do not ship a runtime `AudioSource` path in this game. It cannot work, and it fails silently with a log line per cast.

## Licensing and publication

Source-game assets (models, animations, textures, voice) belong to the source publisher. A character mod that ships them is derivative fan work: credit the publisher, state that it is unofficial, do not claim the art as original, and check the target platform's rules before publishing. Ship your own code under your own license; never redistribute extracted game archives or another project's tools without permission.

## What this route does not cover

- Multiplayer was designed for (form and Rage replicate as buffs, damage goes through the game's systems) but only single-player was tested.
- Shaders: runtime-built materials use the game's standard shader path. Custom shaders need a bundle.
- Performance at very high skin counts was not profiled beyond load time.
- No Unity editor import, retargeting or AssetBundle path was validated here; that remains a separate route.

## No editor, no paid tool: procedural geometry

Not every asset needs an external source. `forge new MyChar --template procedural` scaffolds a tested mesh
generator (noise-displaced icosphere with radius, subdivision and roughness in the config) built from nothing
but the Unity API. It covers placeholders, props and simple shapes — Gnar's boulder is exactly this technique —
and it compiles and runs without Unity, Blender or any licensed software. Reach for it before reaching for an
extractor.

