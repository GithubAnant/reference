"""Tool adapters — where each tool keeps its sessions and memory files.

An ``Adapter`` is pure config: globs for transcripts, the parser format to use,
and globs for memory/instruction files (CLAUDE.md, AGENTS.md, ...). Built-ins
cover Claude Code and Codex. Users/agents extend coverage by dropping a
``reference.toml`` with extra ``[[tool]]`` entries — no code change required for
a tool that uses a known transcript format.
"""

from __future__ import annotations

import glob
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


def _x(p: str) -> str:
    return os.path.expanduser(os.path.expandvars(p))


@dataclass
class Adapter:
    name: str
    session_globs: list[str] = field(default_factory=list)
    session_format: str = "claude"  # claude | codex | generic
    memory_globs: list[str] = field(default_factory=list)
    keep_thinking: bool = True
    enabled: bool = True


# Built-in coverage. Globs use ** (recursive) and ~ expansion.
BUILTINS: list[Adapter] = [
    Adapter(
        name="claude",
        session_globs=[_x("~/.claude/projects/**/*.jsonl")],
        session_format="claude",
        memory_globs=[
            _x("~/.claude/CLAUDE.md"),
            _x("~/.claude/projects/**/memory/*.md"),
        ],
    ),
    Adapter(
        name="codex",
        session_globs=[_x("~/.codex/sessions/**/*.jsonl")],
        session_format="codex",
        memory_globs=[_x("~/.codex/AGENTS.md")],
    ),
]


def config_path() -> Path:
    return Path(_x(os.environ.get("REFERENCE_MCP_CONFIG", "~/.config/reference-mcp/reference.toml")))


def load_adapters() -> list[Adapter]:
    """Return enabled adapters: built-ins merged with the user's ``reference.toml``."""
    by_name: dict[str, Adapter] = {a.name: Adapter(**a.__dict__) for a in BUILTINS}

    cp = config_path()
    if cp.exists():
        try:
            data = tomllib.loads(cp.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            data = {}
        for entry in data.get("tool", []):
            name = entry.get("name")
            if not name:
                continue
            adapter = by_name.get(name) or Adapter(name=name)
            if "session_globs" in entry:
                adapter.session_globs = [_x(g) for g in entry["session_globs"]]
            if "session_format" in entry:
                adapter.session_format = entry["session_format"]
            if "memory_globs" in entry:
                adapter.memory_globs = [_x(g) for g in entry["memory_globs"]]
            if "keep_thinking" in entry:
                adapter.keep_thinking = bool(entry["keep_thinking"])
            if "enabled" in entry:
                adapter.enabled = bool(entry["enabled"])
            by_name[name] = adapter
        for name in data.get("disable", []):
            if name in by_name:
                by_name[name].enabled = False

    return [a for a in by_name.values() if a.enabled]


def iter_files(globs: list[str]) -> list[str]:
    """Resolve globs to a de-duplicated, sorted list of existing files."""
    seen: set[str] = set()
    for pattern in globs:
        for path in glob.glob(pattern, recursive=True):
            if path not in seen and os.path.isfile(path):
                seen.add(path)
    return sorted(seen)
