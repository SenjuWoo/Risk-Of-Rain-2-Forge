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
        first = forge("build", name)
        second = forge("build", name, "--locked", "--offline")
        assert first["assembly_sha256"] == second["assembly_sha256"], "Locked build changed assembly bytes"
        package = forge("package", name)
        repeated = forge("package", name)
        assert package["sha256"] == repeated["sha256"], "Package is not deterministic"
        assert forge("validate", package["archive"])["valid"]
        print(json.dumps({"template": template, "package_sha256": package["sha256"], "warnings": second["warnings"]}))


if __name__ == "__main__":
    main()
