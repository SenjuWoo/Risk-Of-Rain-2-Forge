"""Small JSON CLI shared by human launchers and MCP tools.

Failures return a nonzero exit and one JSON error on stderr; --debug adds a
traceback on stderr. No command installs mods or publishes to a remote service.
"""
import argparse
import json
import sys
import traceback

from . import core


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Agent-first Risk of Rain 2 Forge; JSON output, local source only.")
    result.add_argument("--debug", action="store_true", help="Include a diagnostic traceback on stderr")
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="Discover game, profiles and installed tools without changing them")
    commands.add_parser("updates", help="Check official package feeds on demand without changing pins or installing updates")
    setup = commands.add_parser("setup", help="Install pinned tools locally, reusing existing Python/.NET")
    setup.add_argument("--offline", action="store_true")
    new = commands.add_parser("new", help="Create an owned mod in projects/NAME")
    new.add_argument("name")
    new.add_argument("--author", required=True)
    new.add_argument("--template", choices=["plugin", "stats"], default="plugin")
    new.add_argument("--description", default="A Risk of Rain 2 mod.")
    build = commands.add_parser("build", help="Restore pinned references and compile; never deploy")
    build.add_argument("name")
    build.add_argument("--locked", action="store_true", help="Require an unchanged existing packages.lock.json")
    build.add_argument("--offline", action="store_true", help="Use only the locally restored NuGet package cache")
    symbols = commands.add_parser("symbols", help="Find exact type names without decompiling an entire assembly")
    symbols.add_argument("query")
    symbols.add_argument("--assembly")
    symbols.add_argument("--limit", type=int, default=20)
    bump = commands.add_parser("bump", help="Back up and update a mod's version fields together")
    bump.add_argument("name")
    bump.add_argument("target", help="patch, minor, major, or an explicit increasing X.Y.Z")
    inspect = commands.add_parser("inspect", help="Decompile one exact type with official ILSpy")
    inspect.add_argument("type_name")
    inspect.add_argument("--assembly")
    inspect.add_argument("--member", help="Decompile only this exact XML member ID/token to save context")
    package = commands.add_parser("package", help="Package only this mod's own DLL and package metadata")
    package.add_argument("name")
    validate = commands.add_parser("validate", help="Inspect a Thunderstore ZIP without extracting it")
    validate.add_argument("archive")
    logs = commands.add_parser("logs", help="Read and triage a profile log (latest log by default)")
    logs.add_argument("--path")
    logs.add_argument("--lines", type=int, default=250)
    lookup = commands.add_parser("lookup", help="Read authoritative Thunderstore package metadata")
    lookup.add_argument("namespace")
    lookup.add_argument("name")
    lookup.add_argument("--version")
    guide = commands.add_parser("guide", help="Read the agent workflow or a modding recipe")
    guide.add_argument("topic", nargs="?", default="overview")
    return result


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "setup":
            from .toolchain import setup
            value = setup(offline=args.offline)
        elif args.command == "doctor":
            value = core.doctor()
        elif args.command == "updates":
            from .updates import check_updates
            value = check_updates()
        elif args.command == "new":
            value = core.new_mod(args.name, args.author, args.template, args.description)
        elif args.command == "build":
            value = core.build(args.name, args.locked, args.offline)
        elif args.command == "inspect":
            value = core.inspect(args.type_name, args.assembly, args.member)
        elif args.command == "symbols":
            value = core.symbols(args.query, args.assembly, args.limit)
        elif args.command == "bump":
            from .project_ops import bump
            value = bump(args.name, args.target)
        elif args.command == "package":
            value = core.package_mod(args.name)
        elif args.command == "validate":
            value = core.validate(args.archive)
        elif args.command == "logs":
            value = core.logs(args.path, args.lines)
        elif args.command == "lookup":
            value = core.lookup(args.namespace, args.name, args.version)
        else:
            value = core.guide(args.topic)
        print(json.dumps(value, ensure_ascii=True))
        return 1 if value.get("valid") is False or value.get("complete") is False else 0
    except Exception as exc:
        print(json.dumps({"error": str(exc), "command": args.command, "type": type(exc).__name__}), file=sys.stderr)
        if args.debug:
            traceback.print_exc(file=sys.stderr)
        return 1
