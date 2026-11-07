"""Read Ollama chat events and detect sustained short text repetition."""
import json
import re
from collections import Counter

MIN_REPEATS = 32
MIN_REPEAT_CHARS = 96
MAX_FRAGMENT_CHARS = 32
ROTATION_WINDOW = 24
MAX_SENTENCE_CHARS = 48
TAIL_LIMIT = max(MAX_FRAGMENT_CHARS * MIN_REPEATS, (ROTATION_WINDOW + 1) * (MAX_SENTENCE_CHARS + 2))
SENTENCE_BOUNDARY = re.compile(r"[.!?。！？\r\n]")


def repeated_suffix(text):
    for width in range(1, min(MAX_FRAGMENT_CHARS, len(text) // MIN_REPEATS) + 1):
        count = max(MIN_REPEATS, (MIN_REPEAT_CHARS + width - 1) // width)
        fragment = text[-width:]
        # Repeated HTML/SVG tags and blank whitespace are normal.
        if not fragment.strip() or not set(fragment).isdisjoint("<>\"'="):
            continue
        if text.endswith(fragment * count):
            return {"pattern": "exact_repetition", "fragment_chars": width, "repetitions": count}
    return None


def sentence_rotation(text):
    sentences = [" ".join(part.casefold().split()) for part in SENTENCE_BOUNDARY.split(text)[:-1] if part.strip()]
    window = sentences[-ROTATION_WINDOW:]
    if len(window) < ROTATION_WINDOW or any(
        len(sentence) > MAX_SENTENCE_CHARS
        or not any(character.isalpha() for character in sentence)
        or any(not (character.isalpha() or character in " '’,-") for character in sentence)
        for sentence in window
    ):
        return None
    counts = Counter(window)
    if 2 <= len(counts) <= 6 and min(counts.values()) >= 3:
        return {"pattern": "sentence_rotation", "window_sentences": len(window),
                "distinct_sentences": len(counts)}
    return None


def read_chat_stream(lines):
    tails = {"thinking": "", "content": ""}
    content = []
    chunks = 0
    content_has_markup = False
    for line in lines:
        if not line.strip():
            continue
        event = json.loads(line)
        if not isinstance(event, dict):
            raise ValueError("Invalid Ollama stream event.")
        if "error" in event:
            raise ValueError(str(event["error"]))
        chunks += 1
        message = event.get("message") or {}
        for channel, tail in tails.items():
            delta = message.get(channel)
            if not delta:
                continue
            if channel == "content" and "<" in delta:
                content_has_markup = True
            tails[channel] = (tail + delta)[-TAIL_LIMIT:]
            repeated = repeated_suffix(tails[channel])
            if (not repeated and (channel == "thinking" or not content_has_markup)
                    and SENTENCE_BOUNDARY.search(delta)):
                repeated = sentence_rotation(tails[channel])
            if repeated:
                return {"done": False, "done_reason": "degeneration",
                        "channel": channel, "observed_chunks": chunks, **repeated}
        content.append(message.get("content") or "")
        if event.get("done"):
            return {**event, "message": {"content": "".join(content)}}
    return {"done": False, "observed_chunks": chunks}
