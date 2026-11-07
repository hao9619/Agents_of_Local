"""Generate an HTML artifact through Ollama and deliver it through Continue."""
import argparse
import hashlib
import json
import logging
import os
import re
import sqlite3
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from .context_budget import CONTEXT_WINDOW, RECOVERY_PREFIX, SYSTEM_PROMPT, output_budget, prepare_context
from .generation_guard import read_chat_stream
from .local_knowledge import search
from .task_state import TaskStore

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / ".local" / "artifacts"
CONFIG = ROOT / ".continue" / "mcpServers" / "local-artifacts.local.yaml"
LEGACY_CONFIG = CONFIG.with_suffix(".json")
MCP_TIMEOUT_MS = 900_000
TASK_DATABASE = ROOT / ".local" / "task-state.sqlite3"
OLLAMA = "http://127.0.0.1:11435"
ENTRYPOINT = ROOT / "local_artifacts.py"
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
        os.environ.get("LOCAL_ARTIFACT_API_BASE", OLLAMA).rstrip("/") + "/api/chat",
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


def generate_with_knowledge(task, filename, output, directory, query, *, references=None,
                            generate=generate_html):
    try:
        matches = search(directory, query)
    except OSError as error:
        return {"status": "knowledge_error", "message": str(error)}
    if not matches:
        return {"status": "knowledge_no_match", "knowledge_sources": [],
                "message": "No matching passage. Refine the query or add a relevant document."}
    supplied = list(references or [])
    sources = []
    for match in matches:
        source = f'{match["source"]}:{match["start_line"]}-{match["end_line"]}'
        supplied.append(f'Source: {source}\n{match["text"]}')
        sources.append({"source": match["source"], "start_line": match["start_line"],
                        "end_line": match["end_line"], "reference": len(supplied)})
    result = deliver(task, filename, output, generate, references=supplied)
    context = result.get("context")
    for source in sources:
        source["included"] = (source["reference"] in context["included_references"]) if context else None
    return {**result, "knowledge_sources": sources}


def write_config(path, config):
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
        temp_path = Path(temporary.name)
        try:
            temporary.write((json.dumps(config, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
            temporary.close()
            temp_path.replace(path)
        finally:
            temporary.close()
            temp_path.unlink(missing_ok=True)


def configure_mcp(config_path, legacy_path, *, api_base=None, model=None, timeout=None):
    legacy = json.loads(legacy_path.read_text(encoding="utf-8-sig")) if legacy_path.exists() else {}
    old_servers = legacy.get("mcpServers", {})
    old_entry = old_servers.get("local-artifacts", {})

    # JSON syntax is valid YAML and lets the installer update its own file without extra dependencies.
    config = {"name": "Local Artifacts", "version": "0.0.1", "schema": "v1", "mcpServers": []}
    if config_path.exists():
        config = json.loads(config_path.read_text(encoding="utf-8-sig"))
    servers = config["mcpServers"]
    entry = next((server for server in servers if server["name"] == "local-artifacts"), None)
    if entry is None:
        entry = {"name": "local-artifacts", "type": "stdio"}
        servers.append(entry)
    entry.update(command=sys.executable, args=[str(ENTRYPOINT)])
    entry.setdefault("connectionTimeout", MCP_TIMEOUT_MS)
    if timeout is not None:
        entry["connectionTimeout"] = timeout

    env = {**old_entry.get("env", {}), **entry.get("env", {})}
    if api_base:
        env["LOCAL_ARTIFACT_API_BASE"] = api_base
    if model:
        env["LOCAL_ARTIFACT_MODEL"] = model
    if env:
        entry["env"] = env

    config_path.parent.mkdir(parents=True, exist_ok=True)
    write_config(config_path, config)
    if "local-artifacts" in old_servers:
        del old_servers["local-artifacts"]
        write_config(legacy_path, legacy)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--configure", action="store_true", help="Register this interpreter and script in Continue.")
    parser.add_argument("--api-base", help="Local Ollama-compatible address, e.g. http://127.0.0.1:13305.")
    parser.add_argument("--model", help="Model name for the MCP tool.")
    parser.add_argument("--mcp-timeout-ms", type=int, help="Continue tool timeout in milliseconds (default: 900000).")
    args = parser.parse_args()
    if args.configure:
        if args.mcp_timeout_ms is not None and args.mcp_timeout_ms <= 0:
            parser.error("--mcp-timeout-ms must be positive.")
        try:
            configure_mcp(CONFIG, LEGACY_CONFIG, api_base=args.api_base, model=args.model, timeout=args.mcp_timeout_ms)
        except json.JSONDecodeError as error:
            parser.error(f"Could not read the generated config. Keep its JSON-compatible YAML syntax. {error}")
        print(CONFIG)
        return

    from mcp.server.fastmcp import FastMCP

    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    server = FastMCP("Local Artifacts")
    knowledge_dir = ROOT / os.environ.get("LOCAL_KNOWLEDGE_DIR", ".local/knowledge")
    if not TASK_DATABASE.resolve().is_relative_to(ROOT):
        raise OSError("Task database resolves outside the workspace.")
    tasks = TaskStore(TASK_DATABASE)

    def task_operation(operation, *args):
        try:
            return operation(*args)
        except LookupError as error:
            return {"status": "task_not_found", "message": str(error)}
        except ValueError as error:
            return {"status": "invalid_input", "message": str(error)}
        except (OSError, sqlite3.Error) as error:
            return {"status": "task_storage_error", "message": str(error)}

    @server.tool()
    def start_task(requirements: str, steps: list[str]) -> dict:
        """Save original requirements and planned steps for a new multi-turn task."""
        return task_operation(tasks.create, requirements, steps)

    @server.tool()
    def resume_task(task_id: str | None = None) -> dict:
        """Load a task checkpoint by ID, or list recent tasks if no ID is supplied."""
        if task_id is None:
            return task_operation(lambda: {"status": "listed", "tasks": tasks.recent()})
        return task_operation(tasks.get, task_id)

    @server.tool()
    def complete_task_step(task_id: str, step_number: int, note: str = "") -> dict:
        """Record a completed step using its 1-based number after confirming its outcome."""
        return task_operation(tasks.complete, task_id, step_number, note)

    @server.tool()
    def search_knowledge(query: str) -> dict:
        """Find relevant local Markdown or text snippets with file and line references."""
        try:
            matches = search(knowledge_dir, query)
        except OSError as error:
            return {"status": "knowledge_error", "message": str(error)}
        return {"status": "found" if matches else "no_match", "matches": matches}

    @server.tool()
    def generate_html_file(task: str, filename: str, references: list[str] | None = None,
                           knowledge_query: str | None = None, task_id: str | None = None) -> dict:
        """Save HTML with optional references or knowledge_query. Pass task_id to record the tool result."""
        if task_id is not None:
            state = task_operation(tasks.get, task_id)
            if "task_id" not in state:
                return state
            if not task.strip():
                return {"status": "invalid_input", "message": "Task must be non-empty."}
            task = f'Saved task requirements:\n{state["requirements"]}\n\nCurrent step:\n{task}'
        try:
            if not OUTPUT.resolve().is_relative_to(ROOT):
                raise OSError("Artifact directory resolves outside the workspace.")
            if knowledge_query:
                result = generate_with_knowledge(task, filename, OUTPUT, knowledge_dir,
                                                 knowledge_query, references=references)
            else:
                result = deliver(task, filename, OUTPUT, references=references)
        except OSError as error:
            result = {"status": "storage_error", "message": str(error)}
        if task_id is not None:
            result["task_id"] = task_id
            try:
                tasks.record_delivery(task_id, filename, result)
            except (OSError, LookupError, sqlite3.Error) as error:
                result["task_record_error"] = str(error)
        LOG.info("generate_html_file %s %s", filename, result)
        return result

    server.run(transport="stdio")


if __name__ == "__main__":
    main()
