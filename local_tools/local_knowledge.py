"""Small, dependency-free search over local Markdown and text files."""
import re
from collections import Counter
from math import log
from pathlib import Path

MAX_FILE_BYTES = 128 * 1024
MAX_CHUNK_CHARS = 700
WORD = re.compile(r"[a-z0-9_]+|[\u3400-\u9fff]+")


def terms(text):
    tokens = set()
    for word in WORD.findall(text.casefold()):
        if "\u3400" <= word[0] <= "\u9fff" and len(word) > 1:
            tokens.update(word[i:i + 2] for i in range(len(word) - 1))
        else:
            tokens.add(word)
    return tokens


def passages(text):
    """Yield bounded paragraphs with 1-based inclusive source lines."""
    lines = []
    start = end = size = 0
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip() or size + len(line) + 1 > MAX_CHUNK_CHARS:
            if lines:
                yield start, end, "\n".join(lines)
                lines, size = [], 0
        if not line.strip():
            continue
        if len(line) >= MAX_CHUNK_CHARS:
            for offset in range(0, len(line), MAX_CHUNK_CHARS):
                yield number, number, line[offset:offset + MAX_CHUNK_CHARS]
            continue
        if not lines:
            start = number
        lines.append(line)
        end = number
        size += len(line) + 1
    if lines:
        yield start, end, "\n".join(lines)


def search(directory: Path, query: str, limit: int = 3) -> list[dict]:
    root = directory.resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Knowledge directory does not exist: {root}")
    query_terms = terms(query)
    if not query_terms:
        return []
    candidates = []
    counts = Counter()
    total = 0
    for path in sorted(root.rglob("*")):
        if path.suffix.lower() not in {".md", ".txt"} or path.is_symlink() or not path.is_file():
            continue
        if not path.resolve().is_relative_to(root) or path.stat().st_size > MAX_FILE_BYTES:
            continue
        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            continue
        for start, end, passage in passages(text):
            total += 1
            overlap = query_terms & terms(passage)
            if overlap:
                counts.update(overlap)
                candidates.append((overlap, {
                    "source": path.relative_to(root).as_posix(),
                    "start_line": start, "end_line": end, "text": passage,
                }))
    candidates.sort(key=lambda match: -sum(
        1 + log((total + 1) / (counts[token] + 1)) for token in sorted(match[0])
    ))
    return [passage for _, passage in candidates[:limit]]
