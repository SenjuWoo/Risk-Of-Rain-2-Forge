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

## What counts as tested

Loader `Awake` is not a stage test. An autorun that fires the four skills, swaps skins and logs the aim dot is a mechanics test. The autorun camera is not a gallery. The played run is the acceptance test for look, hover and sound.

Quit-time `NullReferenceException` in `EnableCustomRenderTextureOnLight` and `GenericPool` release, and `ClipCursor` access denied, showed up with this survivor and are not this mod. Filter them before blaming the plugin.
