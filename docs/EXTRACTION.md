# Extracting assets from other games

How to get a character, its animations and its audio out of another game and into Risk of Rain 2 — and, just
as usefully, which parts of that don't work and why.

Everything here is measured, not recalled. Numbers were read from the files on this machine.

## First: what can actually transfer

| Asset | Transferable? | Notes |
|---|---|---|
| Skeletal mesh + skeleton | Yes | Through glTF; see the coordinate trap below |
| Animations | Yes | Same trap, and it is the one that breaks rigs |
| Textures | Yes | Usually DDS/PNG; RoR2 runs the Built-In pipeline |
| Wwise sound **media** | Yes | WEM/WAV decode fine |
| Wwise **bank** | **No**, across Wwise versions | See "Audio" — this is measured, not folklore |
| Materials/shaders | No | Different engine, different shading model |

## UE4 / UE5 games (Marvel Rivals and friends)

Use **CUE4Parse** against the game's `.pak`/IoStore files with its `mappings.usmap`. It is free, open source,
and it reads the real container formats. What you need:

- The game's `Paks` folder and the correct AES key, if the pak is encrypted.
- A `mappings.usmap` matching the game build. A mismatched mapping produces silently wrong property reads, not
  errors — always check that a known asset type deserialises with sensible field values before trusting it.

### The coordinate trap that will cost you a day

UE is **Z-up, X-forward, left-handed**. Unity is **Y-up**. A glTF writer may already apply its own `SwapYZ`,
and if the mesh exporter and the animation exporter apply *different* conventions you get a rig that stands
correctly at rest and twists the moment it animates. That is exactly the bug that was found and fixed on the
Ultron extraction: mesh/bindpose used `(-X, Z, Y)` while animations used `(Y, Z, X)`.

Two rules:

1. Pick **one** transform and apply it to mesh, skeleton, bindpose and every animation channel.
2. Verify it mathematically before baking, per skeleton:

   ```
   for each bone: World(bone) * Bindpose(bone)  must be  identity
   ```

   On the verified Ultron export the maximum error was `0.000000`. If it is not ~0, your transform is wrong and
   no amount of animation work will save it.

Also check the rest pose against frame 0 of an idle clip — the bone transforms should agree. If they don't,
mesh and animation disagree about the skeleton.

### Sizes

A modern hero is not small: the verified Ultron skeleton was **110,637 vertices with 269 joints**. Unity's
 default 16-bit index buffer tops out at 65,535 vertices, so any converted mesh above that needs
`mesh.indexFormat = IndexFormat.UInt32`, or it renders as garbage.

## Audio: the part that doesn't transfer

Wwise banks are version-locked. The version lives in the `BKHD` chunk, and a runtime refuses to load a bank
built for a different one. Measured on this machine:

| Source | BKHD version | Wwise |
|---|---|---|
| Risk of Rain 2 (247 banks) | **150** (`0x96`) | 2023.1 |
| Marvel Rivals hero banks | **145** (`0x91`) | 2022.1 |

So "extract a bank from another game and drop it into RoR2" does not work, even though the file is a perfectly
valid bank and the media inside is fine. Read the version yourself before planning anything:

```python
import struct
head = open(path, "rb").read(12)
assert head[:4] == b"BKHD"
print("version:", struct.unpack_from("<I", head, 8)[0])   # 150 = 2023.1 runtime
```

That leaves three honest routes:

1. **Re-author in Wwise 2023.1.** Decode the source media to WAV, import it, build a bank, load with
   R2API.Sound. Correct and spatialised; needs the Wwise authoring tool (account-gated, see `docs/AUDIO.md`).
2. **Play the decoded media through the OS mixer.** No bank, no version matching, no licence — this is what
   both shipped characters do (Gnar and Ultron). Costs spatialisation and the game's mixer. Documented in
   `docs/AUDIO.md`.
3. **Check whether the source happens to match.** If a game ships 2023.1 banks (version 150), its banks are
   plausibly loadable as-is. Measure first; never assume.

Extracting WEM media is still worth doing in every case: it is the input for route 1 and route 2 alike.

## Checklist

- [ ] Container opened with the right key and a build-matching mappings file
- [ ] One coordinate transform, applied to mesh, skeleton, bindpose and all channels
- [ ] `World * Bindpose == Identity` verified per bone before baking
- [ ] Rest pose matches frame 0 of an idle clip
- [ ] `IndexFormat.UInt32` for anything above 65k vertices
- [ ] BKHD version read before planning any audio work
- [ ] Textures checked against the Built-In render pipeline
- [ ] Nothing proprietary shipped: no game DLLs, no ripped assets you lack the rights to redistribute


## Unity (IL2CPP) games: bake the right prefab, and decrypt what is encrypted

Measured on a survivor port from a Unity 2022.3 IL2CPP game (Manaka, Nov 2026). The first three builds shipped the wrong
character and looked "nothing like the game" until the prefab was checked.

### Check you are baking the player, not a lookalike

- List every `SkinnedMeshRenderer` under the **player prefab** with mesh, vertex count, blend-shape count and material, and
  compare against a screenshot of the real character before baking anything. A game can hold dozens of near-identical
  NPC women (`NpcFemale_*`) whose meshes have no morphs and no player wardrobe. Their data is plausible and wrong.
- Her real body had 42 morphs, the face 280, the coat 15 (open/close, bust). An NPC mesh with `m_Shapes: 0` is the sign
  you are on the wrong prefab. Dressing state (coat open, mask, boots) is usually renderer toggles plus morphs on the
  player prefab, not separate meshes.

### Encrypted AssetBundles

- A streaming bundle that does not start with `UnityFS` and whose bytes look random is encrypted. The decryptor is in the
  game (here an `IKA9nt.Encrypter` `SeekableAesStream`). Do not hunt the key in the binary; ask the game.
- Route that worked: a throwaway BepInEx IL2CPP plugin in the **source game** that waits about 12 s after the title screen,
  reads `EncrypterCore.loadedBundle[label].cryptSystem` (a `SeekableAesStream`) and copies it to disk through `Read`. Harmony
  patching the stream constructor failed ("Failed to init IL2CPP patch backend"); reading the cached stream did not.
- Remove the plugin afterwards and say so: the source game folder must end exactly as found. The decrypted bundle is a
  game asset: keep it out of the package and out of git.
- Interop stubs come from the game's own `BepInEx/interop`; `forge inspect` on that DLL lists the loader's classes.

### Reading the bundle

- UnityPy needs a type-tree generator for IL2CPP bundles without type trees: `TypeTreeGenerator(version)` plus
  `load_local_game(game_dir)`, installed as `env.typetree_generator`. Meshes, materials, textures, Avatars and the
  transform tree read fine. **Humanoid clips do not**: they are stored streamed/dense.
- AssetRipper (headless: `--headless --port N`, then `POST /Settings/Update`, `/LoadFile`, `/Export/UnityProject`) writes
  clips as plain YAML float curves, which is what a runtime muscle driver needs. Export once, bake from the YAML.
- Clip channel names are not `HumanTrait` muscle names for fingers: `LeftHand.Index.1 Stretched` is
  `Left Index 1 Stretched`. Drop the IK goal channels (`LeftFootT/Q`, `RightHandT/Q`...); they are not muscles and made
  the "unmatched channel" count look like a bug.
- Blend-shape curves (`classID 137`, `blendShape.<name>` on a path) carry the face. Bake them with the muscles.
- Take the **Avatar's own T-pose** (`m_Human.m_SkeletonPose`, human scale) for the runtime Avatar and keep the prefab's
  bind pose for the skin. The two differ; using the bind pose tilts every muscle frame.
- The prefab root can scale the whole character (1.2 here). Without it she is a head too short.

### Every bake needs a guard

A baker that falls back silently when its input is missing produces a "working" pack with 127 of 176 clips and zero face
shapes. Fail loudly if the clip export or bundle is absent, and print counts (parts, clips, shapes referenced).
