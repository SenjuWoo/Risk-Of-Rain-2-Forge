"""Regenerate ror2forge/r2api_ownership.json from the upstream R2API repository.

Ownership is derived from the repository tree (module directories plus root-level `<Type>API.cs` files),
never from a memory of package names. Run when R2API publishes a new module; review the diff, then commit.
"""
import datetime
import json
import pathlib
import urllib.request

URL = "https://api.github.com/repos/risk-of-thunder/R2API"
TREE = "https://api.github.com/repos/risk-of-thunder/R2API/git/trees/{ref}?recursive=1"
SKIP = {"Analyzer", "Test", "BuildCI", "libs", "docs", "RoR2"}


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": "RoR2Forge/refresh-ownership", "Accept": "application/vnd.github+json"})
    return json.loads(urllib.request.urlopen(request, timeout=30).read(8 * 1024 * 1024))


def main():
    repo = fetch(URL)
    tree = fetch(TREE.format(ref=repo["default_branch"]))
    types, modules = {}, set()
    for entry in tree["tree"]:
        if not entry["path"].endswith(".cs"):
            continue
        parts = entry["path"].split("/")
        if len(parts) != 2:
            continue
        module, name = parts[0].replace("R2API.", ""), parts[1][:-3]
        if module in SKIP or "." in module:
            continue
        modules.add(module)
        if name.endswith("API"):
            types[name] = module
    types["R2API"] = "Core"
    # Module-root classes that are not named *API.cs. Each entry is checked against upstream by hand.
    curated = {"ContentAddition": "ContentManagement"}
    for name, module in curated.items():
        types[name] = module
    existing = {}
    target_old = pathlib.Path(__file__).resolve().parents[1] / "ror2forge/r2api_ownership.json"
    if target_old.is_file():
        try:
            existing = json.loads(target_old.read_text(encoding="utf-8")).get("curated", {})
        except ValueError:
            existing = {}
    curated.update(existing)
    target = pathlib.Path(__file__).resolve().parents[1] / "ror2forge/r2api_ownership.json"
    target.write_text(json.dumps({
        "source": "https://github.com/risk-of-thunder/R2API",
        "ref": repo["default_branch"],
        "upstream_pushed_at": repo["pushed_at"],
        "generated": datetime.date.today().isoformat(),
        "method": "derived from the repository tree: module directories plus root-level <Type>API.cs files",
        "modules": sorted(modules),
        "types": dict(sorted(types.items())),
        "curated": dict(sorted(curated.items())),
    }, indent=2) + "\n", encoding="utf-8")
    print(f"{len(modules)} modules, {len(types)} types -> {target}")


if __name__ == "__main__":
    main()
