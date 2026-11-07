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
file, line, method, severity and confidence in `forge audit` JSON (`findings[]`).

`FixedUpdate` physics is not flagged. A single allocation is not flagged. If a rule fires on legitimate code, that is
a bug in the rule, not in the mod.

## Measuring instead of guessing

Optimisation claims need numbers from the same machine, game version, graphics settings, mod profile and workload:

1. Baseline run with only the mod that ships the feature and nothing else new.
2. F7 console: `profiler.enable` / `profiler.log` on the frame range that matters (RoR2 ships a profiler stub).
3. Record median and 99th-percentile frame time, `GC.Alloc` per frame, and peak managed heap (`profiler.memory`).
4. Repeat after the change, same map, same stage time, same entity count.
5. Report the delta or report **UNMEASURED**. A green audit is not a measurement.

Do not add a permanent profiler dependency, and do not ship debug instrumentation enabled in a release build.
