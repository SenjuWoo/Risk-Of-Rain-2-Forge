# Survivor runtime lessons

Measured on a second shipped survivor (Ultron, Marvel Rivals assets, played and accepted on 2026-11-01), on top of the body recipe in `CHARACTER_PIPELINE.md`. Re-check type and field names with `forge symbols` / `forge inspect` after a game update. A green compile is not one of these facts.

## The live model is not a child of the body

`ModelLocator` detaches the model from the body (`dontDetatchFromParent` left false, which is the vanilla default). After spawn:

- `GetComponentInParent` from the model does not find the body.
- `transform.IsChildOf(body)` is false.
- The prefab body is inactive. The spawned body is the active object in a loaded scene.

Resolve the live body from `CharacterModel.body` on that active object. Do not cache the prefab's `InputBankTest` and aim with it. The companion, the camera and the skill states all need the spawned survivor.

## A companion that must face the crosshair

Unity is left-handed. `transform.forward` is +Z. `Quaternion.LookRotation(aimDirection)` points +Z at the target.

Set that rotation in `LateUpdate`, on a component with a late `DefaultExecutionOrder` (10000 worked). `CharacterDirection` yaws the parent during the frame and undoes a world rotation written in `Update`. An unparented object, such as a legion drone that is not under the body, keeps an `Update` rotation because nothing yaws it afterwards.

Bank around the aim axis: `Quaternion.AngleAxis(bankDegrees, aimDirection) * look`. When the aim is nearly parallel to world up (`|dot(aim, up)| > 0.985`), pass `Vector3.forward` as the up hint or `LookRotation` flips.

If the glowing face of the mesh is +Z, do not "fix" a backwards drone with `LookRotation(-aim)`. That turns the tail toward the target. If a framed shot shows the tail, yaw the mesh child so the face becomes +Z, then keep `LookRotation(aim)`.

Acceptance for aim is the dot product of the companion's forward and the normalized aim, logged on the live body. `1.000` means that axis points at `GetAimRay().GetPoint(distance)`. A screenshot whose camera sits at the knees does not show facing. A person looking at the model is the visual check.

The aim ray starts inside the hurtbox, so a physics raycast from `GetAimRay()` does not hit the caster. Do not shrink the hurtbox to chase a self-hit you have not measured.

## Camera params are a struct

`CharacterCameraParams.data` must be copied to a local, edited, and assigned back. Writing `params.data.pivotVerticalOffset = ...` changes a copy and the camera never moves.

Size `pivotVerticalOffset` and `idealLocalCameraPos` to the character. Positive local X puts the camera on the character's right. A tall survivor that still uses Commando's pivot renders as a sliver at the bottom of the screen. A runtime `CameraParamsOverrideRequest` can apply the same numbers on the live body.

Put gameplay scale on the rig root of the live model. The detached model does not inherit a scale you set only on the body.

## Skills, buffs and velocity

Create custom `BuffDef`s with `ContentAddition.AddBuffDef` before the states that apply them. Apply the timed buff with `AddTimedBuff` on the server. Remove-then-add refreshes the duration. `RecalculateStats` does not run every frame; the buff add is what updates and replicates the stats.

On `RecalculateStatsAPI.GetStatCoefficients`, these are different fields. Inspect them before copying a number:

- `moveSpeedMultAdd += 0.45f` is +45% move speed. That is the field the flight buff used.
- `moveSpeedTotalMult` starts at `1` and is what the stats template multiplies. Do not apply both fields for one bonus.
- `armorAdd += 60f` is +60 armor.

Do not also multiply `CharacterMotor.velocity` by 1.45 while the buff is active. That stacks a second copy of the bonus. Do not add vanilla `CloakSpeed` (about +40% speed) or vanilla `ArmorBoost` on top. `ArmorBoost` is not "+60 armor".

Two of your own buffs that both add `armorAdd` stack. Flight and a guard buff up together were +120 armor. Decide that on purpose.

If a body controller writes velocity every frame, it erases a dash that a skill just set. Keep a short lock so steering does not run during the burst, and do not run a hover assist during a flight skill that owns the velocity. Hover, when you want it, eases vertical speed toward 0 only while jump is held, the body is airborne, and it is not still rising out of a jump.

A one-shot action clip must win over a locomotion or flight loop override. If the loop writes every frame, the skill animation never plays.

Beam and ring visuals that should track the crosshair belong in `Update`. Damage stays in `FixedUpdate`. Take the beam origin from the firing hand bone on the live rig.

Healing and barrier run only when `NetworkServer.active`. The pulse and the sound run on every client. A client-side heal desyncs the body.

## Authority for motor writes

A body controller that sets `CharacterMotor.velocity` or calls `Motor.ForceUnground()` (flight, hover, dash) must gate it on `body.hasEffectiveAuthority`. Only the owning client simulates that motor; on the host and other clients the writes are discarded at best and fight the network transform at worst. Entity states run on every client, so buffs still go on the server (`NetworkServer.active`) and visuals still run everywhere.

## Damage source

Since Seekers of the Storm, `BulletAttack.damageType` and `BlastAttack.damageType` are `DamageTypeCombo`, and items that key off "primary/secondary/utility/special skill damage" read its `damageSource`. A plain enum converts implicitly and compiles, but carries `DamageSource.NoneSpecified`, so those items ignore the hit. Tag every skill attack:

```csharp
damageType = new DamageTypeCombo(DamageType.IgniteOnHit, DamageTypeExtended.Generic, DamageSource.Primary),
// or, with no extra flags: DamageTypeCombo.GenericSecondary
```

Do not write `DamageTypeCombo.GenericPrimary | DamageType.X`: the implicit conversions make the operator ambiguous. `forge audit` warns on a literal `DamageType.` value with no source.

## Item displays

A survivor whose `CharacterModel.itemDisplayRuleSet` is null shows no items at all. Hand-placing a rule per item is hundreds of rules. The route that works without an editor (Ultron 1.2.0, every costume):

1. Before cloning, read Commando's `CharacterModel.itemDisplayRuleSet` and `ChildLocator` from the original `CommandoBody` prefab. Share the rule set as-is; it is already catalogued, so no clone and no `GenerateRuntimeValues` call.
2. For each Commando child name (32 on the 2026-11 build: `Chest`, `Head`, `ThighL`, `CalfR`, `GunL`, ...), record its rotation relative to the model root and its lossy scale.
3. After your rig is built and still in its rest pose, add an adapter `GameObject` under the matching bone of your skeleton (UE5 mannequin: `Chest`→`spine_04`, `Stomach`→`spine_02`, limbs by side, unknown names→chest). Set the adapter's world rotation to `modelRoot.rotation * commandoRelativeRotation` and its scale to `commandoScale * ratio / bone.lossyScale`, where `ratio` is your head height over Commando's (1.56 m). Register the adapters in your `ChildLocator` under Commando's names.
4. Commando's offsets then land on the same body part. A slim survivor needs a build factor below 1 on `ratio`; pure height scaling left Ultron's hoof and glasses oversized and floating (0.75 fixed it).

Gnar (League rig, two forms) reused this with its own bone map and a build factor of 0.9, and rebuilds the anchors on every rig build and on every Mini/Mega swap. A survivor with several forms or models needs the rebuild on each; the bone map and build factor are the only per-character parts.

If your rig pins bone 0 to identity in its animator, pin it before measuring the rest pose.

Displays attach to transforms of the current rig. When a costume swap or a late `Start` rebuilds the rig, the old displays die with it, and any display requested before the rig existed never spawned. After every rig build call `DisableAllItemDisplays()`, clear the equipment and key-item displays, then `UpdateItemDisplay(body.inventory)` and restore them. Skip all of it while `body.inventory` is null: `CharacterModel.SetEquipmentDisplay` with an unchanged index dereferences `body.inventory` and throws on a fresh body.

Verify with a dev command that calls `inventory.GiveItemString(name, 1)` / `GiveEquipmentString(name)` on the server and screenshots front, side and back. One costume is not every costume; rebuild once and shoot again.

## What the Commando clone drags along

Cloning `CommandoBody` keeps its `SfxLocator`. Clear `deathSound` and `barkSound` when the survivor plays its own death line, or both play. The other fields (landing, jump) are generic.

## Texture memory

`ImageConversion.LoadImage(tex, bytes, false)` keeps a readable CPU copy of every texture beside the GPU one. A survivor with ~130 512² costume textures paid ~180 MB of RAM for nothing. Pass `true` unless code reads the pixels back or compresses them: `LoadImage(..., false)` then `Compress(true)` then `Apply(false, true)` is correct (DXT cuts VRAM ~4x and the last call frees the CPU copy; `forge audit` accepts that pair).  `Sprite.Create` does not need a readable texture.

Check the bake output for byte-identical duplicates (a fallback `model.gz` that equals the default costume's) and maps the material builder drops (`_M`, `_S` masks). Keep them in the source tree; leave them out of the package.

## What counts as tested

Loader `Awake` is not a stage test. An autorun that fires the four skills, swaps skins and logs the aim dot is a mechanics test. The autorun camera is not a gallery. The played run is the acceptance test for look, hover and sound.

Quit-time `NullReferenceException` in `EnableCustomRenderTextureOnLight` and `GenericPool` release, and `ClipCursor` access denied, showed up with this survivor and are not this mod. Filter them before blaming the plugin.

## Flying projectiles are not replicated

A skill state that only moves its projectile under `isAuthority` simulates it on the caster's screen only. Every other player never sees it move, even when the host applies the damage. The pattern that works (Kisame's sharks, Nov 2026):

- Run the skill state on every client, so every client flies its own visual copy.
- Apply damage, eating and healing on the server only (`NetworkServer.active`), keyed off the hit, not off the visual.

Clients grow their own copy by flight time only; only the server's copy grows by eaten projectiles. That split is part of the behavior, not an approximation of it.

## Effects from another game: blend codes and per-vertex color

Storm 4's NUD effect materials store the blend factors directly. For NDP3 they follow Smash Forge's `NudEnums` (`NudEnums.cs`): dst 1 is `OneMinusSrcAlpha` (normal alpha), 2 and 7 are `One` (additive), 3 and 5 are reverse-subtract, 0 is no blend. High bits on the dst value (0xB1) are flags, not factors. Kisame's own body is (2,0) — additive with no dst factor — which is toon water, not glow.

Reading those codes wrong is the expensive failure: a first pass drew alpha layers as additive glow and hid the (2,0) water layers as "multiply", so every effect looked like a bright blob. Check the codes against the source game's own reader before inventing a layer class, and use the character's own body material as a control — it confirms the decoding without a screenshot.

Storm effect meshes also carry tint and edge fades as RGBA per vertex. A bake that keeps only UVs loses the fade, so a soft edge renders as a hard silhouette. Export the RGBA (GMD2 is GMD1 plus one RGBA per vertex) and drive the runtime materials with `DISABLEREMAP` plus `VERTEXCOLOR` plus `VERTEXALPHA`. Boost and bias on the vertex color must stay 1/0: they scale the color too (blown white, or black).

Material animation curves (format 4, 18 floats) carry the UV offset and scale, and slot 16 is the alpha-test reference 0..255. Multiply shadows and second texture layers need Storm's composite shader; leaving them off is a declared gap, not a silent default.

## Automated game runs are bounded

A dev step that throws mid-capture can leave the character on a hidden render layer and stall the script until the run timeout. Every harness step that changes render layers, visibility or camera state restores them in a `finally`, and its own coroutine gets a wait, not the run's remaining time. Cap the run at one or two tries and a few minutes. The first time this was learned it cost about 50 minutes of a stuck dev game (Kisame, Nov 2026).
