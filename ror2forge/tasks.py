"""Task-aware guidance: decide what kind of mod is being built, then load only what it needs.

An agent asking "make Commando deal 10% more" should not be handed the survivor pipeline, the Unity editor route
and the Wwise audio path. This module maps a plain request to the smallest set of categories, documents and
frameworks that actually apply, and states what to avoid. It is data plus a scorer; it generates no C#.
"""
from __future__ import annotations

import re

# Each category lists the words that indicate it, the documents worth reading, the frameworks that matter and
# the checks an agent must run before calling the work finished. `avoid` names the tempting wrong turn.
CATEGORIES: dict[str, dict] = {
    "stats": {
        "words": {"damage": 2, "stat": 2, "stats": 3, "buff multiplier": 2, "more health": 2, "speed": 1,
                  "attack speed": 2, "cooldown": 1, "recalculate": 3, "coefficient": 2, "balance": 1},
        "docs": ["docs/RECIPES.md", "docs/RUNTIME.md"],
        "required": ["R2API.RecalculateStats"],
        "optional": [],
        "checks": ["stat changes applied through the stat-coefficient event, not per-frame field writes",
                   "one subscription, undone on destroy (scene changes must not stack handlers)"],
        "avoid": ["AssetBundles", "Unity editor", "content packs", "per-frame Update loops"],
    },
    "config": {
        "words": {"config": 3, "settings": 2, "option": 2, "toggle": 2, "checkbox": 2, "slider": 1, "risk of options": 3},
        "docs": ["docs/RECIPES.md", "docs/THUNDERSTORE.md"],
        "required": [],
        "optional": ["RiskOfOptions"],
        "checks": ["config entries bound once at Awake; no file I/O in hot paths"],
        "avoid": ["custom UI when the built-in config file is enough", "AssetBundles"],
    },
    "item": {
        "words": {"item": 3, "equipment": 3, "pickup": 2, "inventory": 2, "lunar": 2, "tier": 1, "drop": 1},
        "docs": ["docs/RECIPES.md", "docs/RUNTIME.md", "docs/SURVIVOR_CHECKLIST.md"],
        "required": ["R2API.ContentManagement", "R2API.Items"],
        "optional": ["R2API.Language", "R2API.Prefab", "R2API.RecalculateStats"],
        "checks": ["definition and pickup registered during the content-pack lifecycle",
                   "localization tokens exist for name/description/pickup", "item display rules set on models"],
        "avoid": ["adding to a frozen catalog at runtime", "guessing asset addresses"],
    },
    "buff": {
        "words": {"buff": 3, "debuff": 3, "dot": 1, "status effect": 3, "stack": 1, "bleed": 2, "burn": 2},
        "docs": ["docs/RECIPES.md", "docs/RUNTIME.md"],
        "required": ["R2API.ContentManagement"],
        "optional": ["R2API.RecalculateStats"],
        "checks": ["buff def registered before catalogs finalize", "stacks cleared correctly on removal"],
        "avoid": ["per-frame buff ticking when the game already ticks stacks"],
    },
    "survivor": {
        "words": {"survivor": 4, "character": 3, "playable": 3, "hero": 2, "skin": 2, "loadout": 2},
        "docs": ["docs/CHARACTER_PIPELINE.md", "docs/SURVIVOR_CHECKLIST.md", "docs/RUNTIME.md"],
        "required": ["R2API.ContentManagement", "R2API.Skins", "R2API.Prefab"],
        "optional": ["R2API.Skills", "R2API.Language", "R2API.Networking"],
        "checks": ["body, hurtbox, camera, death state and item displays all set",
                   "skills registered with verified signatures", "every skin has a body/skin pair",
                   "texture memory measured, not assumed"],
        "avoid": ["shipping extracted game content as original work", "URP/HDRP shaders in a built-in pipeline game"],
    },
    "skill": {
        "words": {"skill": 3, "ability": 3, "attack": 1, "cooldown": 2, "special": 1, "secondary": 2, "primary": 2,
                  "loadout": 2},
        "docs": ["docs/CHARACTER_PIPELINE.md", "docs/RUNTIME.md"],
        "required": ["R2API.ContentManagement"],
        "optional": ["R2API.Skills", "R2API.Networking", "R2API.Prefab"],
        "checks": ["skill def fields verified against the assembly", "server authority for damage and spawns",
                   "cooldown/charges behave for host and client"],
        "avoid": ["inventing GenericSkill signatures", "client-side damage application"],
    },
    "enemy": {
        "words": {"enemy": 3, "monster": 3, "ai": 2, "director": 2, "spawn": 2, "boss": 2, "elite": 2},
        "docs": ["docs/RUNTIME.md", "docs/RECIPES.md"],
        "required": ["R2API.ContentManagement", "R2API.Director"],
        "optional": ["R2API.Prefab", "R2API.Networking"],
        "checks": ["spawn cards registered with the director", "AI cost bounded; no per-frame global scans"],
        "avoid": ["FindObjectsOfType in AI update loops", "spawning networked objects without registration"],
    },
    "companion": {
        "words": {"companion": 3, "drone": 3, "minion": 3, "follower": 2, "pet": 2},
        "docs": ["docs/RUNTIME.md", "docs/RECIPES.md"],
        "required": ["R2API.ContentManagement"],
        "optional": ["R2API.Prefab", "R2API.Networking"],
        "checks": ["ownership and lifetime rules", "pathing/update cost measured with many instances"],
        "avoid": ["per-frame searches of every character"],
    },
    "projectile": {
        "words": {"projectile": 3, "bullet": 2, "missile": 2, "beam": 2, "blast": 2, "orb": 1},
        "docs": ["docs/RUNTIME.md", "docs/RECIPES.md"],
        "required": ["R2API.ContentManagement"],
        "optional": ["R2API.Prefab", "R2API.Networking"],
        "checks": ["ghost/prefab references current for 1.5.0+", "authority on the server only"],
        "avoid": ["loading assets per shot", "network spam for cosmetic effects"],
    },
    "stage": {
        "words": {"stage": 3, "map": 2, "scene": 3, "environment": 2, "level": 2, "interactable": 2},
        "docs": ["docs/RECIPES.md", "docs/RUNTIME.md"],
        "required": ["R2API.ContentManagement", "R2API.Stages"],
        "optional": ["R2API.Director"],
        "checks": ["scene name and stage def agree", "monsters and interactables registered for the stage"],
        "avoid": ["rebuilding the scene graph every frame"],
    },
    "procedural": {
        "words": {"procedural": 3, "generated": 2, "geometry": 3, "mesh": 2, "hazard": 2, "modular": 2},
        "docs": ["docs/RUNTIME.md", "docs/RECIPES.md"],
        "required": [],
        "optional": ["R2API.Prefab"],
        "checks": ["mesh and collider cost measured with several instances",
                   "synchronisation only for state other clients must see"],
        "avoid": ["regenerating meshes every frame", "collider-per-vertex", "materials duplicated per instance"],
    },
    "vfx": {
        "words": {"vfx": 3, "particle": 3, "shader": 3, "effect": 2, "trail": 2, "impact": 1},
        "docs": ["docs/RUNTIME.md", "docs/RECIPES.md"],
        "required": [],
        "optional": ["R2API.Prefab"],
        "checks": ["overdraw and particle counts checked in a busy scene", "effect prefabs registered if networked"],
        "avoid": ["unique material per spawned effect", "freezing the game on first spawn to load"],
    },
    "animation": {
        "words": {"animation": 3, "animator": 3, "rig": 2, "clip": 2, "emote": 2},
        "docs": ["docs/CHARACTER_PIPELINE.md", "docs/RUNTIME.md"],
        "required": [],
        "optional": ["R2API.Skins"],
        "checks": ["clips bound to the correct avatar", "animation events verified at runtime"],
        "avoid": ["retargeting at runtime every frame"],
    },
    "audio": {
        "words": {"audio": 3, "sound": 2, "music": 2, "voice": 2, "wwise": 3, "bank": 2},
        "docs": ["docs/AUDIO.md", "docs/RUNTIME.md"],
        "required": [],
        "optional": [],
        "checks": ["route chosen deliberately (Wwise bank vs OS mixer) with its cost stated",
                   "events exist in the shipped map, volume respects the game's SFX slider"],
        "avoid": ["assuming AudioClip/AudioSource works here", "playing sound every frame"],
    },
    "ui": {
        "words": {"ui": 3, "menu": 3, "hud": 3, "panel": 2, "button": 2, "tooltip": 2, "screen": 1},
        "docs": ["docs/RUNTIME.md", "docs/RECIPES.md"],
        "required": [],
        "optional": ["RiskOfOptions"],
        "checks": ["canvas rebuilt only on change", "input works with controller and keyboard"],
        "avoid": ["per-frame layout rebuilds", "blocking the game thread on asset loads"],
    },
    "networking": {
        "words": {"multiplayer": 3, "network": 3, "host": 2, "client": 2, "sync": 3, "late join": 3, "server": 2},
        "docs": ["docs/RECIPES.md", "docs/RUNTIME.md"],
        "required": [],
        "optional": ["R2API.Networking"],
        "checks": ["authority boundary stated per feature", "host and client tested separately",
                   "late join and reconnect tested where supported"],
        "avoid": ["client-authoritative damage or spawns", "replicating unchanged values"],
    },
}

DOC_ORDER = ["docs/CHARACTER_PIPELINE.md", "docs/RECIPES.md", "docs/RUNTIME.md", "docs/SURVIVOR_CHECKLIST.md",
             "docs/AUDIO.md", "docs/THUNDERSTORE.md"]
# Generic documents every route already reads; a category-specific second document (survivor's checklist) is
# essential and must never be squeezed out by a budget.
GENERIC_DOCS = {"docs/RECIPES.md", "docs/RUNTIME.md", "docs/THUNDERSTORE.md"}
MAX_DOCS = 5


def _normalise(text: str) -> str:
    return " " + re.sub(r"[^a-z0-9 ]+", " ", text.lower()) + " "


def classify(text: str) -> list[dict]:
    """Categories that match, best first, each with the words that caused it."""
    haystack = _normalise(text)
    scored = []
    for name, spec in CATEGORIES.items():
        hits, score = [], 0
        for word, weight in spec["words"].items():
            if " %s " % word in haystack:
                hits.append(word)
                score += weight
        if hits:
            scored.append({"category": name, "score": score, "matched": hits})
    return sorted(scored, key=lambda row: (-row["score"], row["category"]))


def plan(text: str) -> dict:
    """The smallest useful briefing for this request: every recognised feature keeps its own document."""
    ranked = classify(text)
    if not ranked:
        return {"request": text, "categories": [], "primary_docs": ["docs/RECIPES.md"],
                "additional_docs": [], "docs": ["docs/RECIPES.md"], "excluded": [],
                "required": [], "optional": [],
                "checks": ["no category matched: read docs/RECIPES.md and decide the route before writing code"],
                "avoid": ["importing frameworks before the route is chosen"], "matched": {}}
    chosen = [row["category"] for row in ranked[:3]]
    excluded = [{"category": row["category"], "score": row["score"], "doc": CATEGORIES[row["category"]]["docs"][0],
                 "action": "add an explicit need for it to the request, or read its document"}
                for row in ranked[3:]]
    # Each chosen category's own document is primary, and a category-specific second document is essential too:
    # a recognised feature never loses its guidance to a reading budget.
    primary = []
    for name in chosen:
        for doc in CATEGORIES[name]["docs"][:2]:
            if doc not in primary and doc not in GENERIC_DOCS:
                primary.append(doc)
    additional, required, optional, checks, avoid = [], [], [], [], []
    for name in chosen:
        spec = CATEGORIES[name]
        for doc in spec["docs"][1:]:
            if doc not in primary and doc not in additional:
                additional.append(doc)
        for dep in spec["required"]:
            if dep not in required:
                required.append(dep)
        for dep in spec["optional"]:
            if dep not in optional and dep not in required:
                optional.append(dep)
        for check in spec["checks"]:
            if check not in checks:
                checks.append(check)
        for item in spec["avoid"]:
            if item not in avoid:
                avoid.append(item)
    for doc in [CATEGORIES[name]["docs"][0] for name in chosen]:
        if doc in GENERIC_DOCS and doc not in additional and doc not in primary:
            additional.append(doc)
    additional.sort(key=lambda doc: DOC_ORDER.index(doc) if doc in DOC_ORDER else len(DOC_ORDER))
    additional = additional[:max(0, MAX_DOCS - len(primary))]
    return {"request": text, "categories": chosen, "primary_docs": primary, "additional_docs": additional,
            "docs": primary + additional, "excluded": excluded, "required": required, "optional": optional,
            "checks": checks, "avoid": avoid,
            "matched": {row["category"]: row["matched"] for row in ranked}}
