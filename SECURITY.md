# Security policy

The main branch is WIP and receives fixes; there are no supported stable releases yet. This tool runs trusted owned build projects. MSBuild inputs can execute code, and an agent's permission to read a mod is not permission to execute it.

Report vulnerabilities privately through [GitHub's private vulnerability reporting](https://github.com/SenjuWoo/Risk-Of-Rain-2-Forge/security/advisories/new). Include the affected commit, reproduction steps, expected boundary and impact. Never include live credentials, private game/profile data or another person's files. If private reporting is unavailable, open an issue asking for a private contact without disclosing exploit details.

Normal bug reports belong in Issues. The forge should keep output inside its owned workspace, preserve source/artifacts, treat installed games/profiles as read-only, and keep MCP off by default. Compile/package validation is not a sandbox for hostile projects or proof of game compatibility.
