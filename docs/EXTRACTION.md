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
