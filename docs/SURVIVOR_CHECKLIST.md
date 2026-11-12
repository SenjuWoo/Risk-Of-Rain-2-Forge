# Survivor checklist

One page for anyone, human or model, building a Risk of Rain 2 survivor. Every row compiled, validated and played a
solo run while it was wrong, in a shipped survivor (Ultron, Gnar; Nov 2026). Treat each row as part of the survivor,
not a polish pass. Details are in the doc named in the last column; `forge audit` checks the rows marked **audit**.

## Before the first line of C#

1. `forge doctor`, then read `forge guide character` (route), `extraction` (another game's files), `runtime`, `audio`
   and `thunderstore` as they apply.
2. `forge symbols` / `forge inspect` every type and member you use. A guessed signature is the usual cause of a mod
   that builds against stubs and fails in game.
3. `forge new NAME --author TEAM`, then work in `projects/NAME`.

## Defaults of a survivor

| # | Default | Skipped, you get | Doc |
|---|---|---|---|
| 1 | `CharacterModel.itemDisplayRuleSet` set (Commando's rule set through per-bone adapters), displays rebuilt after every rig build and costume or form swap, skipped while `body.inventory` is null | Items invisible; a throw on a fresh body. **audit** | RUNTIME, Item displays |
| 2 | Every Bullet/Blast/OverlapAttack `damageType` is a `DamageTypeCombo` with a `DamageSource` | Skill-keyed items ignore the hit. **audit** | RUNTIME, Damage source |
| 3 | Motor writes (`velocity`, `ForceUnground`) behind `body.hasEffectiveAuthority`; buffs and heals behind `NetworkServer.active` | Flight and dash fight the network | RUNTIME, Authority |
| 4 | Cloned `SfxLocator` death and bark cues cleared if you play your own | Two death sounds | RUNTIME, Commando clone |
| 5 | Audio route chosen (Wwise bank, or winmm), gain x `AudioManager.cvVolumeMaster` x `cvVolumeSfx`, camera-distance falloff, correct shutdown order, every `Play_...` key in `events.txt` | Silence, noise, or full volume everywhere. **audit** (volume, events) | AUDIO |
| 6 | `LoadImage(..., true)`, or `LoadImage(false)` then `Compress` then `Apply(false, true)` | A second CPU copy of every texture. **audit** | RUNTIME, Texture memory |
| 7 | Runtime assets under `plugins/NAME/`; bake duplicates and unused masks left out of the zip | Loose files after install, a plugin that dies on a path. `validate` | THUNDERSTORE |
| 8 | `R2API.Utils` is in `R2API_Core`; each other `R2API.<Module>` has its own manifest dependency; one version in manifest, csproj and plugin constant | Plugin never loads for users. **audit** | AGENT_GUIDE |
| 9 | Live body resolved from `CharacterModel.body`; companion aimed in `LateUpdate` with `LookRotation(aim)`; camera params copied, edited, assigned back | A companion or camera that points nowhere | RUNTIME |
| 10 | One stat field per bonus; no second velocity multiply; no vanilla CloakSpeed or ArmorBoost on top | Double speed, double armor | RUNTIME, Skills and buffs |
| 11 | Costumes: data from the game's own material files, no clamp on the skin index, per-skeleton animation state cleared when the mesh changes, rig rebuilt on swap outside `onSkinApplied` | T-pose, wrong colors, only some costumes work | CHARACTER_PIPELINE |
| 12 | Skill text numbers come from the constants the skills use; README follows | Tooltips that lie after a rebalance | CHARACTER_PIPELINE |
| 13 | The character baked from the **player** prefab, checked against a screenshot (renderers, morphs, materials); the bake script fails loudly on missing input | A plainer NPC lookalike; a "working" pack missing most clips | EXTRACTION, Unity section |
| 14 | Body and clothing morphs driven as a pair, range clamped to the measured no-clip limit; hidden overlay submeshes skipped | Skin through the coat, decals drawn | CHARACTER_PIPELINE |
| 15 | Effects use Addressables shaders and an inactive template; each skill's effect seen in a screenshot at the frame it fires | Invisible effects | RUNTIME |
| 16 | Soft-body jiggle per bone (spring on position) tuned from logged displacement | Stiff bust, hair and hips | RUNTIME, Soft-body jiggle |
| 17 | Harness: spawn enemies and compare total HP per skill; four-view portrait camera; wait for the local user | Damage and look guessed from logs | RUNTIME |

## Done means

- `forge audit` reports 0 errors and 0 warnings; `forge build --locked`; `forge package`; `forge validate` on the zip.
- A Debug autorun that fires every skill, applies every costume, gives items (`inventory.GiveItemString`) and
  screenshots front, side and back, with no exception from the mod and no `Missing texture`; a companion's aim dot on
  the live body at 1.000. One costume is not every costume.
- Quit-time `GenericPool`, `EnableCustomRenderTextureOnLight` and `ClipCursor` errors are not the mod.
- A played run is the acceptance test for look, hover and sound. Multiplayer is unproven until two real clients ran
  it. Say what you did not do.
- A shipped version is frozen. Fixes ship as a new version; keep the old zip.
