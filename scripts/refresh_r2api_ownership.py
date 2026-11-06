"""Regenerate ror2forge/r2api_ownership.json from a pinned upstream R2API commit.

Ownership is derived from the repository tree (module directories plus root-level `<Type>API.cs` files), never from
a memory of package names. The upstream commit is resolved first and the tree is fetched by that SHA, so two runs at
different times cannot silently mix revisions. A truncated tree is an error, not a partial result.
"""
import datetime
import json
import pathlib
import sys
import urllib.request

REPO = "https://api.github.com/repos/risk-of-thunder/R2API"
SKIP = {"Analyzer", "Test", "BuildCI", "libs", "docs", "RoR2"}
DEFAULT_CURATED = {
    # Module-root classes that are not named *API.cs. Checked against upstream by hand; kept in the committed file.
    "ContentAddition": "ContentManagement",
}


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": "RoR2Forge/refresh-ownership",
                                                   "Accept": "application/vnd.github+json"})
    return json.loads(urllib.request.urlopen(request, timeout=30).read(8 * 1024 * 1024))


def derive(tree, curated):
    """Type -> module map from one tree, with curated entries applied last so they always take effect."""
    types, modules = {}, set()
    for entry in tree["tree"]:
        path = entry.get("path", "")
        if not path.endswith(".cs"):
            continue
        parts = path.split("/")
        if len(parts) != 2:
            continue
        module, name = parts[0].replace("R2API.", ""), parts[1][:-3]
        if module in SKIP or "." in module:
            continue
        modules.add(module)
        if name.endswith("API"):
            types[name] = module
    types["R2API"] = "Core"
    for name, module in curated.items():
        types[name] = module
    return types, sorted(modules)


def main():
    repo = fetch(REPO)
    branch = repo["default_branch"]
    head = fetch(f"{REPO}/git/ref/heads/{branch}")["object"]["sha"]     # immutable pin, not a moving branch
    tree = fetch(f"{REPO}/git/trees/{head}?recursive=1")
    if tree.get("truncated"):
        raise SystemExit("Upstream tree is truncated; refusing to write a partial ownership map")

    target = pathlib.Path(__file__).resolve().parents[1] / "ror2forge/r2api_ownership.json"
    curated = dict(DEFAULT_CURATED)
    sources = {}
    if target.is_file():
        try:
            previous = json.loads(target.read_text(encoding="utf-8"))
        except ValueError:
            previous = {}
        # Legacy files stored a URL as the value. Keep it as provenance and never as a module name.
        for name, value in (previous.get("curated") or {}).items():
            if isinstance(value, str) and value.startswith("http"):
                sources[name] = value
            elif isinstance(value, str):
                curated[name] = value
        sources.update(previous.get("curated_sources") or {})
    types, modules = derive(tree, curated)

    target.write_text(json.dumps({
        "source": "https://github.com/risk-of-thunder/R2API",
        "ref": branch,
        "commit": head,
        "upstream_pushed_at": repo["pushed_at"],
        "generated": datetime.date.today().isoformat(),
        "method": "derived from the pinned commit's tree: module directories plus root-level <Type>API.cs files",
        "modules": modules,
        "types": dict(sorted(types.items())),
        "curated": dict(sorted(curated.items())),
        "curated_sources": dict(sorted(sources.items())),
    }, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {target.name}: {len(types)} types, {len(modules)} modules at {head[:12]}")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sample = {"tree": [{"path": "R2API.ContentManagement/ContentAddition.cs"},
                           {"path": "R2API.Skins/SkinsAPI.cs"}]}
        built, _ = derive(sample, {"ContentAddition": "ContentManagement"})
        assert built["ContentAddition"] == "ContentManagement", built
        assert built["SkinsAPI"] == "Skins", built
        print("self-test ok:", sorted(built))
    else:
        main()
