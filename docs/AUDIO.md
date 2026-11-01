# Audio in Risk of Rain 2 mods

Everything here is measured against the shipping game, not inferred. If you are adding custom sound to a
survivor, an item or a stage, read this before writing any audio code — the obvious approach does not work.

## The hard fact

**Unity's audio subsystem is disabled in this game.** RoR2 runs on **Wwise 2023.1** only. Consequences:

- `AudioSettings.outputSampleRate` returns **0**.
- `AudioSettings.dspTime` stays **0**.
- `AudioSettings.Reset(...)` does not revive anything.
- `AudioClip.Create(...)` returns a clip with **0 samples, 0 channels**.
- `AudioSource.Play()` sets `isPlaying = false`; `AudioClip.SetData` fails.
- The engine logs, at startup: `Audio system is disabled, so AudioSettings.outputSampleRate cannot be queried. Please check the audio project settings.`

So `AudioClip` + `AudioSource` — the thing every Unity tutorial teaches — cannot be used by a mod here.
This is not a load-order problem, a BepInEx problem or a missing dependency. Do not spend a day on it.

Check it yourself in one run (the Gnar project ships this as a dev command):

```csharp
Log($"rate={AudioSettings.outputSampleRate} dsp={AudioSettings.dspTime:F2}");
var clip = AudioClip.Create("probe", 4410, 1, 44100, false);
Log($"samples={clip.samples} channels={clip.channels}");
```

If `rate=0` and `samples=0`, you are in the same place everyone is.

## Route A — a real Wwise sound bank (correct, needs the Wwise editor)

This is how audio is *supposed* to work: the game's own mixer, spatialisation, ducking, volume sliders, all
of it. It requires **Wwise 2023.1**, which is a multi-gigabyte install behind an Audiokinetic account —
`https://www.audiokinetic.com/en/download`. It cannot be bundled with a mod or with this toolkit.

1. Install Wwise **2023.1.x** (must match the game's major.minor: 2023.1). Check what the game expects:

   ```
   grep -i "WwiseUnity: Wwise(R) SDK Version" "<game>/BepInEx/LogOutput.log"
   ```

   The Gnar session recorded `Wwise(R) SDK Version 2023.1.8 Build 8601`.

2. Create a Wwise project, set the platform to Windows, and import your audio as Sound SFX objects.
   Give each one an Event (e.g. `Play_MyMod_Cast`). Set the Wwise project's **SoundBank settings** to
   generate one bank for the mod.
3. Generate the bank (GUI, or headless with `WwiseConsole.exe` from the install):

   ```
   "C:\Program Files (x86)\Audiokinetic\Wwise 2023.1.x\Authoring\x64\Release\bin\WwiseConsole.exe" ^
       generate-soundbank "<project>.wwu" --platform Windows --output "<out dir>"
   ```

4. Ship the `.bnk` (and its `.txt` metadata if you want to read event IDs) inside your package.
5. Load and post from code with **R2API.Sound**:

   ```csharp
   SoundAPI.SoundBanks.Add("MyMod/mybank.bnk");        // path under the plugin folder
   AkSoundEngine.PostEvent("Play_MyMod_Cast", gameObject);
   ```

   Add `R2API_Sound` to your Thunderstore dependencies.

**Cost:** you need the Wwise editor, and the bank must be rebuilt whenever the game's Wwise version changes.
**Benefit:** everything the game's audio system gives you, for free, forever.

## Route B — an OS output stream (works today, no Wwise)

When you cannot install Wwise, you can bypass both Unity and Wwise and write PCM straight to the Windows
mixer with `winmm` `waveOut`. That is what the Gnar mod does (`src/Audio/OsAudio.cs`, ~250 lines).

**What you get:** audible clips, any number of them mixed together, on any Windows machine, with no
dependency and no account.

**What you give up, and must tell your users:**

- **No spatialisation.** A sound is the same volume everywhere; no distance falloff, no panning.
- **Not in the game's mixer.** The Wwise volume sliders do not move it. Read `volume_sfx` yourself and
  apply it (Gnar does this) or expose your own volume config.
- **Not paused with the game.** You must stop or silence the stream when `Time.timeScale == 0`.
- **One output device**, the system default. Device changes mid-run are not handled.

Use Route B for a character's own voice lines (non-positional is arguably *correct* for your own voice).
Think hard before using it for world sounds.

### Four bugs that will cost you an afternoon

These are real, from the Gnar implementation:

1. **`MMTIME` is 12 bytes, not 8.** It is `wType` plus an 8-byte union. Pass a smaller `cbmmt` and
   `waveOutGetPosition` returns `MMSYSERR_ERROR` — which reads exactly like "no audio is playing".
2. **The device reads the unmanaged buffer, not your managed array.** Fill a `short[]` for the mix, then
   `Marshal.Copy` it into the `lpData` allocation from `WAVEHDR`. If you forget, the device plays
   **uninitialised heap memory**: a loud, high-pitched, snare-like noise. This is the single most likely
   cause of "my mod makes a horrible noise".
3. **`waveOutReset` before `waveOutClose`.** Closing with buffers still queued leaves the driver replaying
   the last block — the "beep beep beep" on exit. Reset first, then join your mixer thread, then close.
4. **Stop writing before you reset.** If the mixer thread keeps calling `waveOutWrite` during shutdown it
   re-queues buffers behind the reset and the noise comes back.

### Verifying it without ears

You cannot hear the game from an agent session, so verify the numbers:

- Log `waveOutGetPosition` before and after a second — it must advance by ~44100 samples.
- Meter the **peak of the exact buffer you hand to `waveOutWrite`** (after the `Marshal.Copy`), not the
  managed array, or you will "verify" audio the device never received.
- Optionally dump the device bytes to a `.pcm` and check them: peak > 0, zero-crossing rate in the speech
  range (~0.05–0.15), not ~0.5 (that is noise).

A silence dump at startup is normal — nothing is playing yet. Gate the dump on `peak > 0` or you will
capture nine seconds of nothing and conclude the pipeline is broken.

## Checklist

- [ ] Confirm the engine state first (`outputSampleRate`, `AudioClip.Create`). Do not guess.
- [ ] Decided Route A or Route B, and wrote down the trade-off in the README.
- [ ] Clips are 16-bit PCM WAV at a known sample rate; mono keeps the mixer trivial.
- [ ] Volume exposed in config, and the game's `volume_sfx` read where possible.
- [ ] Stream silenced when `Time.timeScale == 0`.
- [ ] Shutdown: stop writing → reset → join → unprepare → close.
- [ ] Verified: position advances, peak non-zero, no noise burst on quit.

## Getting audio out of another game

See `docs/EXTRACTION.md`. Its banks are version-locked and will not load here — the media will.
