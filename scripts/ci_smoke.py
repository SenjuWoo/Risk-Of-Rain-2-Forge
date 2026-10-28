"""Exercise real clean-checkout builds and packages without a game install.

Run after forge setup. Failures retain normal forge diagnostics in CI output.
"""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def forge(*args):
    result = subprocess.run([sys.executable, str(ROOT / "forge.py"), *args], cwd=ROOT, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return json.loads(result.stdout)


def main():
    for name, template in (("CIPlugin", "plugin"), ("CIStats", "stats")):
        forge("new", name, "--author", "ForgeCI", "--template", template)
        source = ROOT / "projects" / name / "src/Plugin.cs"
        source.write_text(source.read_text(encoding="utf-8").replace("PluginVersion = ", "PluginVersion="), encoding="utf-8")
        fixture = ROOT / "projects" / name / "src/LookupFixture.cs"
        fixture.write_text(f"namespace @{name}; public class LookupFixture {{ public class Nested {{ }} }} public enum LookupFlag {{ None }} public interface ILookupMarker {{ }} public struct LookupValue {{ }} public delegate void LookupCallback();", encoding="utf-8")
        first = forge("build", name)
        second = forge("build", name, "--locked", "--offline")
        assert first["assembly_sha256"] == second["assembly_sha256"], "Locked build changed assembly bytes"
        package = forge("package", name)
        repeated = forge("package", name)
        assert package["sha256"] == repeated["sha256"], "Package is not deterministic"
        assert forge("validate", package["archive"])["valid"]
        found = forge("symbols", f"{name}.", "--assembly", first["assembly"], "--limit", "200")
        names = {item["name"] for item in found["symbols"]}
        for symbol in ("LookupFixture+Nested", "LookupFlag", "ILookupMarker", "LookupValue", "LookupCallback"):
            assert f"{name}.{symbol}" in names, f"ILSpy did not discover {symbol}"
        inspected = forge("inspect", f"{name}.LookupFixture+Nested", "--assembly", first["assembly"])
        assert "class Nested" in inspected["source"]
        changed = forge("bump", name, "patch")
        assert changed["version"] == "1.0.1"
        stale = subprocess.run([sys.executable, str(ROOT / "forge.py"), "package", name], cwd=ROOT, capture_output=True, text=True)
        assert stale.returncode == 1 and "build again" in stale.stderr, "Changed version must require a rebuild"
        rebuilt = forge("build", name, "--locked", "--offline")
        upgraded = forge("package", name)
        assert rebuilt["version"] == "1.0.1" and upgraded["archive"] != package["archive"]
        assert Path(package["archive"]).is_file(), "Bump removed the previous release"
        assert forge("validate", upgraded["archive"])["valid"]
        print(json.dumps({"template": template, "package_sha256": upgraded["sha256"], "symbols": len(names), "version": rebuilt["version"], "warnings": second["warnings"]}))


if __name__ == "__main__":
    main()
