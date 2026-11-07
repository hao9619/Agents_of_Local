"""Generate an HTML artifact through Ollama and deliver it through Continue."""
import argparse
import hashlib
import json
import logging
import os
import re
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from context_budget import CONTEXT_WINDOW, RECOVERY_PREFIX, SYSTEM_PROMPT, output_budget, prepare_context
from generation_guard import read_chat_stream

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / ".local" / "artifacts"
CONFIG = ROOT / ".continue" / "mcpServers" / "local-artifacts.local.json"
OLLAMA = "http://127.0.0.1:11435"
MODEL = "local-coder-4060-9b"
LOG = logging.getLogger(__name__)
WINDOWS_DEVICES = {"CON", "PRN", "AUX", "NUL", *(
    f"{prefix}{number}" for prefix in ("COM", "LPT") for number in range(10)
)}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def generate_html(task):
    budget = output_budget()
    payload = {
        "model": os.environ.get("LOCAL_ARTIFACT_MODEL", MODEL),
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": task},
        ],
        "stream": True,
        "think": False,
        "options": {"num_ctx": CONTEXT_WINDOW, "num_predict": budget, "temperature": 0.2},
    }
    request = urllib.request.Request(
        OLLAMA + "/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=300) as response:
        return read_chat_stream(response)


def publish_new(path, data):
    """Expose a complete file atomically, failing if the destination exists."""
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
        temp_path = Path(temporary.name)
        try:
            temporary.write(data)
            temporary.close()
            if os.name == "nt":
                # Windows rename fails rather than replacing an existing target.
                temp_path.rename(path)
            else:
                os.link(temp_path, path)
        finally:
            temporary.close()
            temp_path.unlink(missing_ok=True)


def deliver(task, filename, output, generate=generate_html, *, references=None):
    if not task.strip():
        return {"status": "invalid_input", "message": "Task must be non-empty."}
    if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}\.html", filename)
            or Path(filename).stem.upper() in WINDOWS_DEVICES):
        return {"status": "invalid_input", "message": "Use a simple HTML filename, e.g. pelican.html."}

    output.mkdir(parents=True, exist_ok=True)
    target = output / filename
    receipt = output / (filename + ".receipt.json")
    references = references or []
    task_identity = json.dumps([task, references], ensure_ascii=False) if references else task
    task_hash = digest(task_identity.encode("utf-8"))
    conflict = {"status": "conflict", "path": str(target),
                "message": "An existing file or receipt does not match this task."}
    if target.exists() or target.is_symlink() or receipt.exists() or receipt.is_symlink():
        if target.is_file() and receipt.is_file() and not (target.is_symlink() or receipt.is_symlink()):
            try:
                previous = json.loads(receipt.read_text(encoding="utf-8"))
                if previous == {"task": task_hash, "sha256": digest(target.read_bytes())}:
                    return {"status": "reused", "path": str(target), "generated_tokens": 0}
            except (OSError, ValueError):
                pass
        return conflict

    try:
        reserved = output_budget()
    except ValueError as error:
        return {"status": "invalid_config", "message": str(error)}
    prompt_task, context = prepare_context(task, references, reserved)
    if context["estimated_input"] > context["input_limit"]:
        return {"status": "context_overflow", "context": context,
                "message": "The task alone exceeds the input budget. Shorten or split the task."}

    start = time.monotonic()
    attempts = []
    for prompt in (prompt_task, RECOVERY_PREFIX + prompt_task):
        attempt_start = time.monotonic()
        try:
            reply = generate(prompt)
        except (OSError, ValueError) as error:
            attempts.append({"finish_reason": "backend_error", "generated_tokens": None,
                             "elapsed_seconds": round(time.monotonic() - attempt_start, 3)})
            return {"status": "backend_error", "message": str(error), "attempts": attempts, "context": context,
                    "elapsed_seconds": round(time.monotonic() - start, 3)}
        attempt = {"finish_reason": reply.get("done_reason"),
                   "generated_tokens": reply.get("eval_count"),
                   "elapsed_seconds": round(time.monotonic() - attempt_start, 3)}
        if "pattern" in reply:
            attempt["pattern"] = reply["pattern"]
        if "prompt_eval_count" in reply:
            attempt["prompt_tokens"] = reply["prompt_eval_count"]
        attempts.append(attempt)
        if attempt["finish_reason"] != "degeneration":
            break

    stats = {**attempt, "attempts": attempts, "context": context,
             "elapsed_seconds": round(time.monotonic() - start, 3)}
    if stats["finish_reason"] == "degeneration":
        details = {key: reply[key] for key in (
            "channel", "observed_chunks", "pattern", "fragment_chars", "repetitions",
            "window_sentences", "distinct_sentences",
        ) if key in reply}
        return {"status": "degeneration", **stats,
                **details,
                "message": "Sustained repetition detected again after one retry. No file was saved."}
    if stats["finish_reason"] == "length":
        return {"status": "truncated", **stats, "message": "Output budget reached. Final file was not saved."}
    content = (reply.get("message") or {}).get("content")
    if not reply.get("done") or stats["finish_reason"] != "stop" or not isinstance(content, str) or not content.strip():
        return {"status": "incomplete", **stats, "message": "No complete generation was returned."}

    data = content.strip().encode("utf-8")
    try:
        publish_new(target, data)
    except FileExistsError:
        return {**conflict, **stats}
    try:
        record = json.dumps({"task": task_hash, "sha256": digest(data)}).encode("utf-8")
        publish_new(receipt, record)
    except OSError as error:
        return {"status": "receipt_error", "path": str(target), **stats,
                "message": f"File saved but completion record failed: {error}"}
    return {"status": "saved", "path": str(target), **stats}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--configure", action="store_true", help="Register this interpreter and script in Continue.")
    args = parser.parse_args()
    if args.configure:
        CONFIG.parent.mkdir(parents=True, exist_ok=True)
        config = {"mcpServers": {"local-artifacts": {
            "command": sys.executable, "args": [str(Path(__file__).resolve())],
        }}}
        CONFIG.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(CONFIG)
        return

    from mcp.server.fastmcp import FastMCP

    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    server = FastMCP("Local Artifacts")

    @server.tool()
    def generate_html_file(task: str, filename: str, references: list[str] | None = None) -> dict:
        """Save one HTML file. Provide a task, a simple .html filename, and optional reference snippets in priority order."""
        try:
            if not OUTPUT.resolve().is_relative_to(ROOT):
                raise OSError("Artifact directory resolves outside the workspace.")
            result = deliver(task, filename, OUTPUT, references=references)
        except OSError as error:
            result = {"status": "storage_error", "message": str(error)}
        LOG.info("generate_html_file %s %s", filename, result)
        return result

    server.run(transport="stdio")


if __name__ == "__main__":
    main()
