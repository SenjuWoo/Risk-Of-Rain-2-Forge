# Task routing for agents

Tell the forge what you are building before you read anything:

```
forge plan "create a new playable survivor with 20 skins and a flying companion"
```

It returns the categories it recognised, the **four most relevant documents** (never the whole docs tree), the
frameworks that actually apply, the checks that must pass, and the tempting wrong turns to avoid. The classifier is
data in `ror2forge/tasks.py`; add a category there rather than in prose.

## Categories

| Category | Typical request | Loads | Frameworks that matter |
|---|---|---|---|
| `stats` | "Commando deals 10% more" | RECIPES, RUNTIME | R2API.RecalculateStats |
| `config` | "a settings toggle" | RECIPES, THUNDERSTORE | RiskOfOptions (optional) |
| `item` / `buff` | custom item, debuff | RECIPES, RUNTIME, SURVIVOR_CHECKLIST | ContentManagement, Items, Language |
| `survivor` | playable character | CHARACTER_PIPELINE, SURVIVOR_CHECKLIST, RUNTIME | ContentManagement, Skins, Prefab |
| `skill` | attacks and cooldowns | CHARACTER_PIPELINE, RUNTIME | ContentManagement (+Networking) |
| `enemy` / `companion` | monster, drone | RUNTIME, RECIPES | ContentManagement, Director |
| `projectile` | bullet, blast | RUNTIME, RECIPES | ContentManagement, Prefab |
| `stage` | new map | RECIPES, RUNTIME | ContentManagement, Stages |
| `procedural` | generated hull, hazard | RUNTIME, RECIPES | Prefab (optional) |
| `vfx` / `animation` | particles, clips | RUNTIME / CHARACTER_PIPELINE | Prefab / Skins |
| `audio` | sound, Wwise bank | AUDIO, RUNTIME | none |
| `ui` | menu, HUD | RUNTIME, RECIPES | RiskOfOptions (optional) |
| `networking` | host/client, late join | RECIPES, RUNTIME | Networking |

A request can match several. The top three are merged, documents are capped at four, and required packages are
unioned — so "survivor with skins and a network sync" does not silently pull in every framework in the registry.

## Per-frame work: what the audit warns about

`forge audit` reports **warnings**, never errors, for these — an `Update` loop is often the correct answer:

| Pattern in `Update` / `FixedUpdate` / `LateUpdate` | Why | Fix |
|---|---|---|
| `FindObjectsOfType`, `FindObjectsByType` | scans the scene every frame | cache once, or react to an event |
| `GameObject.Find`, `FindWithTag` | name lookup every frame | resolve in `Awake`, keep the field |
| `Resources.Load` | synchronous load each frame | load during initialisation, unload explicitly |
| `GetComponent<…>` | component lookup each frame | cache in a field |
| LINQ (`Where`, `Select`, `ToList`, `Any`, …) | allocates every call (medium confidence) | hand-written loop or precomputed list |

Comments and string literals never trip these — the scanner reads comment-stripped code, and every finding carries
file, line, method, severity and confidence in `forge audit` JSON (`findings[]`), and the audit always reports
`findings_total`; the default view shows 12, `--findings-limit N` raises it, and `findings_truncated` says whether
anything was held back.

`FixedUpdate` physics is not flagged. A single allocation is not flagged. If a rule fires on legitimate code, that is
a bug in the rule, not in the mod.

## Measuring instead of guessing

**What the base game gives you.** The developer console opens with `Ctrl+Alt+~` (US/UK layout) and is then toggled with
`~`; `help` lists every command, `find <text>` searches them. Those commands handle game state, not profiling:
`fps_max` caps the frame rate, it does not report frame time. Mods can add their own commands (DebugToolkit adds a
console and many debug commands; it is not a profiler). The base game ships no `profiler.*` command, and this forge
will not pretend one exists.

**What to use instead.** Measure from inside your own mod, behind a debug switch that is off in a release:

| Want | How | Honest limits |
|---|---|---|
| Frame time | `Time.unscaledDeltaTime` sampled every frame into a fixed ring buffer; log median and 99th percentile once a second | sampling itself costs a little; the log line, not the sample, is what distorts |
| CPU time of one method | `System.Diagnostics.Stopwatch` around the call, log total and worst case | only the code you wrapped |
| GC pressure | `GC.CollectionCount(0)` and `GC.GetTotalMemory(false)` once a second | allocation volume, not which code allocated |
| Load time | BepInEx timestamps in `BepInEx/LogOutput.log` between two of your own log lines | includes everything else loading at that moment |
| Live inspection | RuntimeUnityEditor, or BepInEx's debugger (`debug_enabled=true` in `BepInEx/config/BepInEx.cfg`, per the R2Wiki debugging page) | interactive tools, not evidence, and never a shipped dependency |

Log through BepInEx (`Logger.LogInfo`), never `Debug.Log` per frame, and gate the instrumentation behind a config entry
that defaults to off.

**A comparison you can trust:** same machine, same game version, same graphics settings, same mod list, same stage, the
same elapsed stage time, the same entity count. Record the number, change one thing, record it again. Report the delta —
or report **UNMEASURED**. A green audit is not a measurement, a single run is not a trend, and no profiler output is
quoted here because none was taken.

**Do not** add a profiler dependency to the Forge or to a mod's release build, and do not install debugging tools into a
mod-manager profile on someone's behalf.
