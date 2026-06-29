"""Command-line entry point.

    reference-mcp            # run the MCP server over stdio (default; what hosts call)
    reference-mcp serve      # same as above, explicit
    reference-mcp doctor     # list configured tools + how many files each resolves to
    reference-mcp install X  # print the config snippet to register Reference in tool X
"""

from __future__ import annotations

import sys

from . import __version__

_SNIPPETS = {
    "claude": (
        "Claude Code — run:\n"
        "    claude mcp add reference -- uvx --from git+https://github.com/Kuberwastaken/reference reference-mcp\n"
        "or add to ~/.claude.json (mcpServers):\n"
        '    "reference": { "command": "uvx", "args": ["--from", '
        '"git+https://github.com/Kuberwastaken/reference", "reference-mcp"] }'
    ),
    "codex": (
        "Codex CLI — add to ~/.codex/config.toml:\n"
        "    [mcp_servers.reference]\n"
        '    command = "uvx"\n'
        '    args = ["--from", "git+https://github.com/Kuberwastaken/reference", "reference-mcp"]'
    ),
    "cursor": (
        "Cursor — add to ~/.cursor/mcp.json (or .cursor/mcp.json in a project):\n"
        '    { "mcpServers": { "reference": { "command": "uvx", "args": ["--from", '
        '"git+https://github.com/Kuberwastaken/reference", "reference-mcp"] } } }'
    ),
    "vscode": (
        "VS Code (MCP) — add to .vscode/mcp.json:\n"
        '    { "servers": { "reference": { "command": "uvx", "args": ["--from", '
        '"git+https://github.com/Kuberwastaken/reference", "reference-mcp"] } } }'
    ),
}


def _doctor() -> int:
    from .adapters import iter_files, load_adapters

    print(f"Reference v{__version__}\n")
    for a in load_adapters():
        print(f"- {a.name} [format={a.session_format}]")
        print(f"    sessions: {len(iter_files(a.session_globs))} file(s)  via {a.session_globs}")
        print(f"    memory:   {len(iter_files(a.memory_globs))} file(s)  via {a.memory_globs}")
    return 0


def _install(tool: str) -> int:
    key = tool.lower()
    if key not in _SNIPPETS:
        print(f"No built-in snippet for {tool!r}. Known: {', '.join(_SNIPPETS)}.")
        print("For any MCP host, run the command: uvx --from git+https://github.com/Kuberwastaken/reference reference-mcp")
        return 1
    print(_SNIPPETS[key])
    return 0


def main() -> int:
    args = sys.argv[1:]
    cmd = args[0] if args else "serve"
    if cmd in ("serve", "stdio"):
        from .server import serve

        serve()
        return 0
    if cmd == "doctor":
        return _doctor()
    if cmd == "install":
        if len(args) < 2:
            print("usage: reference-mcp install <claude|codex|cursor|vscode>")
            return 1
        return _install(args[1])
    if cmd in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    if cmd in ("-V", "--version", "version"):
        print(__version__)
        return 0
    print(f"unknown command {cmd!r}. Try: reference-mcp --help")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
