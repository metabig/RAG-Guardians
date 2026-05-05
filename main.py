#!/usr/bin/env python3
"""
main.py — Autonomous RAG benchmark agent.

The agent runs in an infinite loop:
  1. Calls the LLM (with tool use enabled).
  2. Executes any tools the model requests.
  3. Feeds results back into the conversation.
"""

import json
import sys
import time
from typing import Any, cast

from env import LM_STUDIO_BASE_URL, MODEL_NAME, SANDBOX_DIR
from tools import (
    TOOLS,
    tool_append_to_file,
    tool_create_file,
    tool_delete_file,
    tool_execute_shell_command,
    tool_list_sandbox_files,
    tool_read_file_windowed,
    tool_wrap_file_lines,
)
from utils import build_client, now_iso

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an autonomous research and continuous improvement agent. Your task is:
1. GENERATE A PLAN: Create a current PLAN.md to answer further users questions about the content of rag_source.txt.
2. EXECUTE THE PLAN: Use your tools to execute the plan. Tools include reading files in sandbox/, creating/updating files, executing shell commands, and listing files.
3. EVALUATE AND IMPROVE: After executing, evaluate the results. If the plan was successful, update PLAN.md with reflections and improvements for next time. If it failed, analyze
what went wrong and generate an improved plan. Always log your reasoning and reflections in PLAN.md.
4. REPEAT: No cycle limit. Regenerate, evaluate, replan, improve continuously.

CRITICAL RULES:
- File reading: ALWAYS specify start_line and end_line. If the file is large, read in small windows.
- If a read requests more than 10k characters, you will receive an error and must split into smaller windows.
- If raw rag_source has very long lines, or if read_file_windowed hits character limits repeatedly, call wrap_file_lines first (default 100 chars/line), then read the wrapped file.
- Each read includes metadata: total lines, lines read, whether more content exists.
- DO NOT ASSUME you have read the complete file in a single read.
- No cycle limit: you can run indefinitely, regenerate plans, compact, etc.
- All created files go to sandbox/."""

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_CONSECUTIVE_ERRORS = 10
BACKOFF_BASE_SECONDS = 5     # First retry waits 5 s; doubles each time, capped at 40 s.
BACKOFF_MAX_DOUBLINGS = 3    # 5 * 2^3 = 40 s maximum wait.

# ---------------------------------------------------------------------------
# Tool dispatch
# ---------------------------------------------------------------------------

# Maps tool name → callable so dispatch is O(1) and easy to extend.
TOOL_REGISTRY: dict[str, Any] = {
    "read_file_windowed":   tool_read_file_windowed,
    "wrap_file_lines":      tool_wrap_file_lines,
    "create_file":          tool_create_file,
    "append_to_file":       tool_append_to_file,
    "delete_file":          tool_delete_file,
    "list_sandbox_files":   tool_list_sandbox_files,
    "execute_shell_command": tool_execute_shell_command,
}


def dispatch_tool(tool_name: str, tool_args: dict) -> dict:
    """Look up and call a tool by name. Returns an error dict for unknown tools."""
    handler = TOOL_REGISTRY.get(tool_name)
    if handler is None:
        return {"ok": False, "error": f"Unknown tool: {tool_name}"}
    return handler(**tool_args)

# ---------------------------------------------------------------------------
# LLM call helpers
# ---------------------------------------------------------------------------

def call_llm(client: Any, messages: list[dict]) -> Any:
    """Call the LLM and return the response object."""
    return client.chat.completions.create(
        model=MODEL_NAME,
        messages=cast(Any, messages),
        tools=cast(Any, TOOLS),
        tool_choice="auto",
        temperature=0.2,
    )


def serialize_assistant_message(assistant_message: Any) -> dict:
    """Convert the OpenAI response message to a plain dict for the message history."""
    tool_calls = [
        {
            "id": tc.id,
            "type": "function",
            "function": {
                "name": tc.function.name,        # type: ignore[union-attr]
                "arguments": tc.function.arguments,  # type: ignore[union-attr]
            },
        }
        for tc in (assistant_message.tool_calls or [])
    ]
    msg: dict[str, Any] = {"role": "assistant", "content": assistant_message.content or ""}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return msg


def build_tool_result_message(tool_call_id: str, result: dict) -> dict:
    """Wrap a tool result in the format the API expects."""
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": json.dumps(result, ensure_ascii=False),
    }


def record_assistant_reply(messages: list[dict], response: Any) -> tuple[list[dict], Any]:
    assistant_message = response.choices[0].message
    messages.append(serialize_assistant_message(assistant_message))
    print(f"[{now_iso()}] Response: {(assistant_message.content or 'no content')[:100]}...")
    return messages, assistant_message

def execute_tool_calls(assistant_message: Any, messages: list[dict]) -> None:
    if assistant_message.tool_calls:
        for tool_call in assistant_message.tool_calls:
            tool_name = cast(Any, tool_call).function.name
            tool_args = json.loads(cast(Any, tool_call).function.arguments)
            print(f"  → Tool: {tool_name} {str(tool_args)[:80]}...")

            result = dispatch_tool(tool_name, tool_args)
            messages.append(build_tool_result_message(tool_call.id, result))

            status = "✓" if result.get("ok") else "✗"
            print(f"    {status} {str(result)[:80]}...")
# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main() -> None:
    SANDBOX_DIR.mkdir(parents=True, exist_ok=True)

    client = build_client()

    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]

    print(f"[{now_iso()}] Starting main.py in autonomous continuous mode...")
    print(f"[{now_iso()}] Sandbox : {SANDBOX_DIR}")
    print(f"[{now_iso()}] Model   : {MODEL_NAME}")
    print()

    iteration = 0
    consecutive_errors = 0

    while True:
        iteration += 1
        print(f"\n=== ITERATION {iteration} ===")

        # ---- Call the LLM (with exponential backoff on failure) ----
        backoff = BACKOFF_BASE_SECONDS * (2 ** min(consecutive_errors, BACKOFF_MAX_DOUBLINGS))
        print(f"[{now_iso()}] Calling {MODEL_NAME}...")

        try:
            response = call_llm(client, messages)
            consecutive_errors = 0
        except Exception as e:
            consecutive_errors += 1
            print(f"✗ ERROR (attempt {consecutive_errors}/{MAX_CONSECUTIVE_ERRORS}): {str(e)[:200]}")

            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                print(f"[{now_iso()}] Too many consecutive errors — exiting.")
                sys.exit(1)

            print(f"[{now_iso()}] Waiting {backoff}s before retry...")
            time.sleep(backoff)
            continue

        # ---- Record the assistant reply ----
        messages, assistant_message = record_assistant_reply(messages, response)

        # ---- Execute requested tool calls ----
        execute_tool_calls(assistant_message, messages)

        print(f"[{now_iso()}] Iteration {iteration} completed.")


if __name__ == "__main__":
    print("=" * 80)
    print("main.py — Autonomous Benchmark with Infinite Self-Improvement Loop")
    print("=" * 80)
    print(f"Current time : {now_iso()}")
    print(f"Sandbox      : {SANDBOX_DIR}")
    print(f"Model        : {MODEL_NAME}")
    print(f"API URL      : {LM_STUDIO_BASE_URL}")
    print()
    print("Requirements:")
    print("  1. LM Studio running at http://127.0.0.1:1234")
    print(f"  2. Model '{MODEL_NAME}' loaded")
    print("  3. Virtualenv active: source .venv/bin/activate")
    print()
    print("The script retries automatically if LM Studio is unavailable.")
    print("Press Ctrl+C to stop.")
    print("=" * 80)
    print()
    main()
