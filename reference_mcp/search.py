"""Search engine — offline BM25-lite ranking over sessions and memory files.

No embeddings, no native deps: a compact BM25 with a recency boost. Parsed
transcripts are cached per file by mtime, and the ranking index
is rebuilt only when the set of files (or their mtimes) changes — so repeated
queries in a session are cheap.
"""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from .adapters import Adapter, iter_files, load_adapters
from .normalize import PARSERS, Message

_WORD = re.compile(r"[a-z0-9_]+")
_STOP = set(
    "the a an and or of to in is are was were be been being this that these those it its "
    "for on with as at by from i you we they he she them our your my me do does did not no "
    "yes can could should would will just if then else so but how what why when where which".split()
)


def tokens(text: str) -> list[str]:
    return [w for w in _WORD.findall(text.lower()) if len(w) > 1 and w not in _STOP]


# ---------------------------------------------------------------------------
# Per-file parse cache + index cache
# ---------------------------------------------------------------------------

_FILE_CACHE: dict[str, tuple[float, list[Message]]] = {}
_INDEX: "Index | None" = None
_INDEX_SIG: tuple | None = None


@dataclass
class Hit:
    message: Message
    score: float


class Index:
    def __init__(self, messages: list[Message]):
        self.messages = messages
        self.docs = [tokens(m.text) for m in messages]
        self.df: dict[str, int] = {}
        for doc in self.docs:
            for term in set(doc):
                self.df[term] = self.df.get(term, 0) + 1
        self.n = len(messages)
        self.avgdl = (sum(len(d) for d in self.docs) / self.n) if self.n else 0.0

    def _idf(self, term: str) -> float:
        df = self.df.get(term, 0)
        return math.log(1 + (self.n - df + 0.5) / (df + 0.5))

    def search(
        self,
        query: str,
        source: str | None = None,
        project: str | None = None,
        role: str | None = None,
        since: datetime | None = None,
        limit: int = 10,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> list[Hit]:
        q = tokens(query)
        if not q:
            return []
        ql = query.lower()
        now = datetime.now(timezone.utc)
        hits: list[Hit] = []
        for msg, doc in zip(self.messages, self.docs):
            if source and msg.source != source:
                continue
            if role and msg.role != role:
                continue
            if project and project.lower() not in (msg.project or "").lower():
                continue
            if since and msg.ts and msg.ts < since:
                continue
            if not doc:
                continue
            dl = len(doc)
            score = 0.0
            for term in q:
                tf = doc.count(term)
                if not tf:
                    continue
                idf = self._idf(term)
                score += idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / (self.avgdl or 1)))
            if score <= 0:
                continue
            if ql in msg.text.lower():  # exact-phrase bonus
                score *= 1.6
            if msg.ts:  # recency boost
                age = (now - msg.ts).days
                if age <= 7:
                    score *= 1.25
                elif age <= 30:
                    score *= 1.1
            hits.append(Hit(msg, score))
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:limit]


def _gather() -> tuple[list[Message], tuple]:
    """Parse all configured transcripts (cached by mtime) and return them plus a
    signature describing the current file set, used to invalidate the index."""
    adapters: list[Adapter] = load_adapters()
    wanted: dict[str, tuple[str, bool]] = {}  # path -> (format, keep_thinking)
    for a in adapters:
        for f in iter_files(a.session_globs):
            wanted[f] = (a.session_format, a.keep_thinking)

    for stale in [p for p in _FILE_CACHE if p not in wanted]:
        del _FILE_CACHE[stale]

    messages: list[Message] = []
    sig: list[tuple[str, float]] = []
    for path, (fmt, keep) in wanted.items():
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue
        cached = _FILE_CACHE.get(path)
        if not cached or cached[0] != mtime:
            parser = PARSERS.get(fmt, PARSERS["generic"])
            try:
                parsed = list(parser(path, keep_thinking=keep))
            except Exception:
                parsed = []
            _FILE_CACHE[path] = (mtime, parsed)
        messages.extend(_FILE_CACHE[path][1])
        sig.append((path, mtime))
    return messages, tuple(sorted(sig))


def get_index() -> Index:
    global _INDEX, _INDEX_SIG
    messages, sig = _gather()
    if _INDEX is None or sig != _INDEX_SIG:
        _INDEX = Index(messages)
        _INDEX_SIG = sig
    return _INDEX


def snippet(text: str, query: str, width: int = 240) -> str:
    low = text.lower()
    pos = -1
    for term in tokens(query):
        pos = low.find(term)
        if pos != -1:
            break
    if pos == -1:
        pos = 0
    start = max(0, pos - width // 3)
    chunk = text[start : start + width].replace("\n", " ").strip()
    prefix = "…" if start > 0 else ""
    suffix = "…" if start + width < len(text) else ""
    return f"{prefix}{chunk}{suffix}"


# ---------------------------------------------------------------------------
# Memory / instruction-file search (CLAUDE.md, AGENTS.md, memory/*.md)
# ---------------------------------------------------------------------------


@dataclass
class MemoryHit:
    source: str
    path: str
    score: float
    snippet: str


def memory_files() -> list[tuple[str, str]]:
    """Return (source, path) for every configured memory/instruction file."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for a in load_adapters():
        for f in iter_files(a.memory_globs):
            if f not in seen:
                seen.add(f)
                out.append((a.name, f))
    return out


def search_memory(query: str, source: str | None = None, limit: int = 10) -> list[MemoryHit]:
    q = set(tokens(query))
    if not q:
        return []
    hits: list[MemoryHit] = []
    for src, path in memory_files():
        if source and src != source:
            continue
        try:
            text = open(path, "r", encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        # Score by chunk (paragraph) so the snippet is the most relevant section.
        best_score, best_chunk = 0.0, ""
        for chunk in re.split(r"\n\s*\n", text):
            ct = tokens(chunk)
            if not ct:
                continue
            overlap = sum(ct.count(t) for t in q)
            if query.lower() in chunk.lower():
                overlap += 5
            if overlap > best_score:
                best_score, best_chunk = overlap, chunk
        if best_score > 0:
            hits.append(MemoryHit(src, path, best_score, best_chunk.strip()[:400]))
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:limit]


# ---------------------------------------------------------------------------
# Session listing / retrieval
# ---------------------------------------------------------------------------


def list_sessions(source: str | None = None, project: str | None = None, limit: int = 20) -> list[dict]:
    messages, _ = _gather()
    by_path: dict[str, dict] = {}
    for m in messages:
        if source and m.source != source:
            continue
        if project and project.lower() not in (m.project or "").lower():
            continue
        info = by_path.setdefault(
            m.path,
            {"source": m.source, "session_id": m.session_id, "project": m.project, "path": m.path, "count": 0, "last_ts": None},
        )
        info["count"] += 1
        if m.project and not info["project"]:
            info["project"] = m.project
        if m.ts and (info["last_ts"] is None or m.ts > info["last_ts"]):
            info["last_ts"] = m.ts
    rows = list(by_path.values())
    rows.sort(key=lambda r: (r["last_ts"] or datetime.min.replace(tzinfo=timezone.utc)), reverse=True)
    return rows[:limit]


def get_session_messages(session_ref: str) -> list[Message]:
    """Find a session by id substring or file path and return its messages in order."""
    messages, _ = _gather()
    ref = session_ref.strip()
    matched = [m for m in messages if ref in m.session_id or ref in m.path]
    return matched
