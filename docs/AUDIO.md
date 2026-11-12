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
mixer with `winmm` `waveOut`. All four survivors built with this kit use this route (Gnar, Ultron, Kisame, Manaka), each in
`src/Audio/OsAudio.cs` plus a small cue/gain wrapper.

**What you get:** audible clips, any number of them mixed together, on any Windows machine, with no
dependency and no account.

**What you give up, and must handle or tell your users:**

- **No engine spatialisation.** Wwise never sees the sound. Distance falloff and left/right pan have to be
  computed by you (below); there is no HRTF, occlusion or reverb.
- **Not in the game's mixer.** The Wwise volume sliders do not move it. Read them yourself (below) and/or
  expose your own volume config.
- **Not paused with the game.** Silence the stream when `Time.timeScale == 0`.
- **One output device**, the system default. Device changes mid-run are not handled.

Two mixer designs have shipped. Pick the first unless you need very little code:

| Design | Used by | Format | Pros | Cons |
|---|---|---|---|---|
| **One stream, managed mix**: one `waveOut` handle, 4 rotating buffers, a thread sums every voice | Gnar (44.1 kHz mono), Manaka (48 kHz stereo) | any one fixed format | Unlimited voices, per-voice gain/pan, delayed starts, click-free stop, pause by not advancing voices | ~250 lines, a thread to shut down correctly |
| **One handle per clip**: 12 `waveOut` handles, each plays a whole clip, oldest stolen when all are busy | Ultron, Kisame (48 kHz stereo) | fixed | Short, no thread | 12-voice cap, no pan or pause, footsteps or rapid fire steal voices |

Whatever the design, bake every clip to the mixer's one format offline (sample rate, channels, 16-bit) and
refuse anything else at load with a log line. Log the first device or write failure once; a swallowed error
looks like a silent mod.

### Volume, distance and pan

Ultron's 1.0–1.1 builds ignored the volume slider and played every Ultron in the lobby at full level in every
ear; 1.1.2 fixed both. Start from this:

```csharp
// Wwise owns the sliders; WinMM bypasses Wwise, so apply them yourself. GetString() returns "0".."100".
static float Slider(RoR2.ConVar.BaseConVar cv) =>
    cv != null && float.TryParse(cv.GetString(), NumberStyles.Float, CultureInfo.InvariantCulture, out var v)
        ? Mathf.Clamp01(v / 100f) : 1f;
float gain = volume * Slider(AudioManager.cvVolumeMaster) * Slider(AudioManager.cvVolumeSfx);

// Distance: fall off against the nearest scene camera (full inside 12 m, silent past 80 m).
Transform cam = null; float best = float.MaxValue;
foreach (var rig in CameraRigController.readOnlyInstancesList)
    if (rig && rig.sceneCam) { float d = Vector3.Distance(rig.sceneCam.transform.position, at); if (d < best) { best = d; cam = rig.sceneCam.transform; } }
if (cam) gain *= 1f - Mathf.Clamp01((best - 12f) / 68f);

// Pan (stereo mixer only): -1 left .. 1 right against that camera. Balance law: the far ear drops and the
// near ear stays at full level, so a centred sound is not louder than a panned one.
float pan = cam ? Mathf.Clamp(Vector3.Dot((at - cam.position).normalized, cam.right), -1f, 1f) * 0.75f : 0f;
float left = gain * (1f - Mathf.Max(0f, pan)), right = gain * (1f + Mathf.Min(0f, pan));
```

`AudioManager.cvVolumeMaster` and `cvVolumeSfx` are static `VolumeConVar`s (checked in the 2026-11 `RoR2.dll`).
Parse invariant: on a comma-decimal locale a slider value of `55.5` otherwise reads as 555. `GetString()`
allocates, so cache the product for half a second.

- **Own body centred, everyone else positioned.** Skill states run on every client, so each client plays its own
  copy. Pass no position when `body.hasEffectiveAuthority && body.isPlayerControlled` (your character), a world
  position otherwise. Lobby and UI sounds take no position.
- **Footsteps fade sooner** (Manaka: silent past 35 m); they are clutter at range.
- **Pause:** set the mixer's pause flag from `Time.timeScale <= 0.01f` every frame. In a one-stream mixer, output
  silence and do not advance voices, so a clip resumes where it stopped (Manaka measured: peak 0 and voices kept
  while paused, playback resumed after).
- **Stop with a fade.** A voice cut mid-sample clicks; Manaka fades 30 ms (1440 frames) when a channelled skill
  is interrupted.
- **Per-shot allocation:** in the handle-per-clip design, scale samples straight into the unmanaged `lpData`
  buffer (an `unsafe` loop) instead of allocating a scaled `short[]` per shot; a 1 MB voice line was 1 MB of
  garbage every play. A one-stream mixer applies gain while summing and never copies the clip.

### Footsteps without animation events

A runtime muscle/bone driver has no Animator, so there are no footstep events. Detect contacts from the pose:
per foot, track the ankle height in rig space and its recent lowest value (`low = min(low + dt * 0.05, h)`);
arm when the ankle rises 6 cm above `low`, fire when an armed ankle comes back within 2.5 cm, and only while
grounded, moving and not in an action clip. This stays on the clip's contacts at any stride speed, which clip
phase does not. Pick the take by outfit (shoes, sneakers, bare feet) when the source game has them.

The bugs below apply to either design.

### Five bugs that will cost you an afternoon

These are real, from the Gnar implementation (3 and 4 only concern a mixer with a thread):

1. **`MMTIME` is 12 bytes, not 8.** It is `wType` plus an 8-byte union. Pass a smaller `cbmmt` and
   `waveOutGetPosition` returns `MMSYSERR_ERROR` — which reads exactly like "no audio is playing".
2. **The device reads the unmanaged buffer, not your managed array.** Fill a `short[]` for the mix, then
   `Marshal.Copy` it into the `lpData` allocation from `WAVEHDR`. If you forget, the device plays
   **uninitialised heap memory**: a loud, high-pitched, snare-like noise. This is the single most likely
   cause of "my mod makes a horrible noise".
3. **`waveOutReset` before `waveOutClose`.** Closing with buffers still queued leaves the driver replaying
   the last block — the "beep beep beep" on exit.
4. **Join the mixer thread before you reset.** Clearing a `_running` flag does not stop a thread that is
   already inside `Write`: it queues one more buffer *after* `waveOutReset`, then you unprepare and
   `FreeHGlobal` memory the device still owns. Order: clear the flag → join the thread → reset →
   unprepare → free → close. (Gnar 1.3.0 had reset before join; fixed in 1.3.1.)
5. **An event key that is not in the map is silent.** Nothing throws when `Play("Play_vo_X")` misses the
   event map, so a typo or an event the source game never had just plays nothing. Gnar's transform voice
   did this for a release. `forge audit` now fails every `"Play_..."` literal that is not a key in the
   shipped `events.txt`. A project with its own cue map (Manaka's `cues.txt`) is not covered by that check:
   log an unknown cue once at runtime instead.

### Verifying it without ears

You cannot hear the game from an agent session, so verify the numbers:

- Log `waveOutGetPosition` (`TIME_SAMPLES`) before and after a second: it must advance by about the stream's
  sample rate (44,100 or 48,000).
- Meter the **peak of the exact buffer you hand to `waveOutWrite`** (after the `Marshal.Copy`), not the
  managed array, or you will "verify" audio the device never received.
- Optionally dump the device bytes to a `.pcm` and check them: peak > 0, zero-crossing rate ~0.05–0.15 for
  speech (Manaka's cloth and water Foley measured 0.147), not ~0.5 (that is noise).
- For panning and distance, play a cue at a point to the camera's right, left and far away and log the
  computed gain and pan (Manaka: ±0.67 pan at 10 m sideways, faded at 40 m, silent at 100 m).
- Debug harness `walk` input is unreliable: the player controller overwrites the scripted move vector, and a
  person touching the focused game window drives the character. Do not judge footsteps or locomotion audio from
  a scripted walk alone.

A silence dump at startup is normal — nothing is playing yet. Gate the dump on `peak > 0` or you will
capture nine seconds of nothing and conclude the pipeline is broken.

## Checklist

- [ ] Confirm the engine state first (`outputSampleRate`, `AudioClip.Create`). Do not guess.
- [ ] Decided Route A or Route B, and wrote down the trade-off in the README.
- [ ] Clips baked offline to the mixer's one format (16-bit PCM, fixed rate and channel count); anything else refused at load.
- [ ] Gain multiplied by `AudioManager.cvVolumeMaster` x `cvVolumeSfx` (`forge audit` warns when a project calls `waveOutWrite` and never reads the SFX slider), and other players' sounds attenuated by camera distance (not audited).
- [ ] Own character centred, other players' characters positioned (and panned, with a stereo mixer).
- [ ] Stream silenced when `Time.timeScale == 0`.
- [ ] Shutdown (mixer with a thread): clear flag → join mixer thread → reset → unprepare → free → close.
- [ ] `forge audit` passes: every played `Play_...` event exists in `events.txt`.
- [ ] Verified: position advances, peak non-zero, no noise burst on quit.

## Getting audio out of another game

See `docs/EXTRACTION.md`. A Wwise bank is version-locked and will not load here; the media will. Unity games:
the AudioClips decode with UnityPy (section "Unity AudioClips" there).
