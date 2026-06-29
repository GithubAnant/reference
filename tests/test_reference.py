"""Tests for parsing + cross-tool search. Run: `uv run --with pytest pytest -q`."""

from pathlib import Path

from reference_mcp import normalize
from reference_mcp.search import Index, tokens

FIX = Path(__file__).parent / "fixtures"


def test_parse_claude():
    msgs = list(normalize.parse_claude(str(FIX / "claude_sample.jsonl")))
    roles = [m.role for m in msgs]
    assert roles == ["user", "assistant", "assistant"]
    assert msgs[0].source == "claude"
    assert "pg necessity" in msgs[0].text.lower()
    # thinking + text both captured on the assistant turn
    assert "[thinking]" in msgs[1].text and "vertical prior" in msgs[1].text
    # tool_use truncated/tagged, not dropped
    assert "[tool:Bash]" in msgs[2].text


def test_parse_codex():
    msgs = list(normalize.parse_codex(str(FIX / "codex_sample.jsonl")))
    assert [m.role for m in msgs] == ["user", "assistant"]
    assert msgs[0].source == "codex"
    assert "gemini grounding" in msgs[0].text.lower()
    # task_started and other non-message events are skipped
    assert all(m.role in ("user", "assistant") for m in msgs)


def test_cross_tool_search():
    msgs = list(normalize.parse_claude(str(FIX / "claude_sample.jsonl")))
    msgs += list(normalize.parse_codex(str(FIX / "codex_sample.jsonl")))
    idx = Index(msgs)

    rzp = idx.search("razorpay pg necessity gate")
    assert rzp and rzp[0].message.source == "claude"

    gem = idx.search("gemini grounding signals")
    assert gem and gem[0].message.source == "codex"

    # source filter works
    only_codex = idx.search("gemini", source="codex")
    assert only_codex and all(h.message.source == "codex" for h in only_codex)
    assert idx.search("gemini", source="claude") == []


def test_tokens_drop_stopwords():
    assert "the" not in tokens("the gemini grounding")
    assert "gemini" in tokens("the gemini grounding")
