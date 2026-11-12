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

The same goes for a skill's own timed buff. `if (isAuthority) characterBody.AddTimedBuff(...)` works when the host plays the survivor and silently does nothing for every other player: for a client-owned body the authority is the client, and `AddTimedBuff` is ignored off the server. Grant it from the server's copy of the state (`if (!granted && NetworkServer.active && fixedAge >= t)`), and keep flashes and sounds outside any authority check so every client shows them. Manaka 1.3.0 had both bugs (Golden Rain, Toy Overload); fixed in 1.4.0.

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

## A dash belongs in rootMotion, not in Motor.SetPosition

`characterMotor.Motor.SetPosition(p)` is a teleport. It skips the kinematic controller's sweep, so a rush that writes it every frame passes through walls, floats over ledges, and — measured on Kisame 1.1.0 — ends under the terrain and drops the survivor out of the map. Writing `velocity` in the same frame applies the distance a second time.

The vanilla pattern (`EntityStates.Huntress.BlinkState`) is the one to copy:

```csharp
characterMotor.velocity = Vector3.zero;                 // nothing else moves him
characterMotor.rootMotion += dir * step;                // BeforeCharacterUpdate runs Motor.MoveCharacter
characterMotor.moveDirection = Vector3.zero;
characterDirection.moveVector = dir;                    // keep facing the rush
```

`rootMotion` is consumed in `BeforeCharacterUpdate` and passed through `Motor.MoveCharacter`, which collides and slides, so the rush follows terrain and stops at walls. Two things this taught:

- Do not add your own forward `SphereCast` to cap the step on top of it. A 0.4 m sphere at hip height clipped rising ground and cut an 18 m rush to 7.4 m; the controller already sweeps.
- A slope costs horizontal distance, because part of the displacement goes into climbing. A state that ends at `fixedAge >= duration` therefore arrives short uphill. Give the step about 15% headroom and end at `traveled >= distance || fixedAge >= duration * 1.2`. Measured 18.29 m against an 18 m target with the headroom; `grounded` stayed true throughout.

Invulnerability for a dash: increment `HurtBoxGroup.hurtBoxesDeactivatorCounter` on the model and decrement it in `OnExit`. Do not set `HealthComponent.godMode` (it also blocks fall damage and self-damage) and do not disable the main hurtbox collider by hand (an interrupted state can leak it). A cooldown refund belongs in `GenericSkill.AddOneStock()`, not in direct writes to `stock` and `rechargeStopwatch`.

## Cloth on a baked rig

A rig baked to a custom pack has no Unity cloth asset and no Animator controller, so a cape or robe hangs perfectly rigid. Two things are needed, and both are cheap:

- **Motion.** Rotate the cloth bones yourself in `LateUpdate`, in world space, from the body's motion: ground speed, vertical speed and turn rate, smoothed. World-space `Quaternion.AngleAxis` around the character's right axis and world up is orientation-independent; local-axis guesses swing the cape sideways. Apply the delta to `bone.rotation` after the clip pose is written, with a `DefaultExecutionOrder` above the driver's. Build the chain list by name (`cloth`, `cape`, `skirt`), give each bone a depth, and fall the swing off with depth so the chain curves instead of hinging rigidly.
- **A visible inside.** Cloth is usually one layer of triangles. With a one-sided material the inside is culled, so the cape disappears when the camera looks up at it. Append a reversed-winding copy of the cloth submesh with flipped normals and the same UVs and bone weights, in the mesh builder. That costs one layer of triangles and works with any shader; it does not depend on a cull property that a given RoR2 shader may not have. Measured on a cape of 3,222 and 14,493 vertices: exactly 2x after the append, and the outside is unchanged because the copy faces inward.

Select the affected submeshes by weight, not by name or material: any vertex bound to a cloth bone. A submesh that borrows a few cloth-weighted vertices is not the cape.

## A projectile ultimate has to burst on contact

Great Shark Bullet only detonated at the end of its 2.2 s travel. Fired at a boss 11 m away it flew about 35 m, exploded behind the player and dealt nothing — measured, not assumed. A projectile that is supposed to hit what you aim at needs a contact test every step (overlap at its own radius, `FriendlyFireManager.ShouldSplashHitProceed` for the team filter), with the end-of-travel burst kept as the fallback.

The blast also used `FalloffModel.SweetSpot`, so only the middle of the radius took the advertised number; the tooltip promised the full figure. Use `FalloffModel.None` when the tooltip states one number for the blast.

## Automated game runs are bounded

A dev step that throws mid-capture can leave the character on a hidden render layer and stall the script until the run timeout. Every harness step that changes render layers, visibility or camera state restores them in a `finally`, and its own coroutine gets a wait, not the run's remaining time. Cap the run at one or two tries and a few minutes. The first time this was learned it cost about 50 minutes of a stuck dev game (Kisame, Nov 2026).


## Soft-body jiggle (bust, hips) without a physics asset

Rotating bone chains with a shared pendulum read as stiff. What works (Manaka 1.3.0, tuned by logged displacement and
screenshots at different phases of a jog): one underdamped spring per bone on **position**.

- Each frame set the bone back to its rest local position, read where the animation puts it (`bone.position`), pull a
  virtual point toward it with `acc = k * (target - p) - c * v` (sub-step at 8 ms, clamp `dt` to 50 ms), then place the bone
  at `target + clamp(offset * gain, max)`. Any motion leaves it lagging and overshooting: steps, landings, clip poses.
- Starting values: `k` 300, `c` 5.5 (zeta about 0.16, several visible bounces), gain 2.3, max 6 cm; child bone `k` 220,
  gain 1.2, max 3.5 cm. Shape the response in the rig's axes so vertical dominates (x 0.8, y 1.4, z 1.0).
- Process parent before child: the child's target already contains the parent's displacement, which is the second wobble.
- Skill states should kick it (`velocity += dir * strength * 0.2`); a full-strength impulse saturates the clamp.
- Verify with a logged displacement per bone over time (idle is millimetres, a pose is tens) and stills at different
  phases. A single screenshot cannot show bounce.

## A survivor with its own camera needs a verification camera of its own

`CameraRigController` owns `Camera.main` every frame, so moving it or pushing a params override from a harness fails. A
dev portrait camera is a second `Camera` (`CopyFrom(main)`, higher depth) placed around the model, ray-checked against
world geometry so terrain cannot sit between lens and subject, destroyed in a `finally`. Frame by joint (head, chest,
hand), not by guessed offsets. Four views (front, side, back, close-up) are the minimum for a model change.

## Harness operations that paid for themselves

`spawn <addressable SpawnCard> N dist` (DirectorCore with `PlacementMode.Direct`, monster team), `hp` (total monster health),
`give Item:N`, `equip`, `shape NAME W` (force a morph every frame), `bust N`, `jlog N dt`, `walk secs`. Damage is judged by
total monster HP before and after each skill, not by a screenshot. The harness must wait for a local `NetworkUser` (up to
90 s) before scripting: the user profile loads late and a fixed 3 s wait fails intermittently with "no local user".

## Locomotion thresholds

RoR2 survivors mostly move at 7 m/s. Choose the jog clip above about 4 m/s and walk below; scale playback by speed over the
clip's stride speed. Thresholds near sprint speed leave the character walking at normal run speed.

## Counting enemies: bodies, not colliders

An overlap query returns every hurtbox. Count distinct `CharacterBody` instances or a multi-hurtbox boss counts several
times. `forge audit` also flags `GetComponent` inside `FixedUpdate`; move the scan into its own method.
