# Contributing

Thanks for helping make cross-tool recall work everywhere. The most valuable
contributions are **new tool adapters**.

## Dev setup

```bash
git clone https://github.com/Kuberwastaken/reference
cd reference
uv venv && uv pip install -e .
uv run reference-mcp doctor          # should list your real tools
uv run --with pytest pytest -q       # tests
```

## Add a tool adapter

1. **Adapter** — add an `Adapter(...)` to `BUILTINS` in `reference_mcp/adapters.py` with the
   tool's `session_globs`, `session_format` (`claude` | `codex` | `generic`), and `memory_globs`.
2. **Parser** — only if none of the existing formats fit: add a `parse_<tool>` generator in
   `reference_mcp/normalize.py` that yields `Message` records, and register it in `PARSERS`.
   Truncate-and-tag tool output (don't dump file contents); skip non-message events.
3. **Tests** — add a tiny `tests/fixtures/<tool>_sample.jsonl` and a parse + search test in
   `tests/test_reference.py`.
4. **Docs** — add the register snippet to `README.md` and to `_SNIPPETS` in `reference_mcp/cli.py`.
5. `uv run --with pytest pytest -q` must pass.

## Conventions

- Standard library only where possible; the sole runtime dependency is `mcp`.
- Keep it local-first and read-only — never write to user transcripts, never network.
- Small, sequential commits with conventional messages (`feat:`, `fix:`, `docs:`, `test:`).

## Agents

If an AI agent set up Reference for a previously-unsupported tool, it is instructed (see
`AGENTS.md` §C) to open a PR adding the adapter. Those PRs are welcome — please include where
the tool stores sessions/memory so it can be verified.
