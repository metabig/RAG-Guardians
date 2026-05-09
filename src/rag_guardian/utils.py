import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from openai import OpenAI

from .env import CHARS_PER_TOKEN_APPROX, MAX_CONTEXT_TOKENS, OPENAI_API_KEY, OPENAI_BASE_URL, SANDBOX_DIR, TRACE_LOG_PATH


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def build_client() -> OpenAI:
    return OpenAI(base_url=OPENAI_BASE_URL, api_key=OPENAI_API_KEY)


def resolve_sandbox_path(relative_path: str, must_exist: bool = False) -> Path:
    """Validate that path is within sandbox/ (security)."""
    candidate = (SANDBOX_DIR / relative_path).resolve()
    sandbox_root = SANDBOX_DIR.resolve()
    if not str(candidate).startswith(str(sandbox_root)):
        raise ValueError(f"Path escapes sandbox: {relative_path}")
    if must_exist and not candidate.exists():
        raise ValueError(f"File not found: {relative_path}")
    return candidate


def read_file_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def read_file_lines(path: Path) -> list[str]:
    return read_file_text(path).splitlines()


def write_file_text(path: Path, content: str, append: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if append:
        with path.open("a", encoding="utf-8") as f:
            f.write(content)
    else:
        path.write_text(content, encoding="utf-8")


def append_trace(event: dict[str, Any]) -> None:
    """Log tool invocation to audit trail."""
    event["timestamp"] = now_iso()
    write_file_text(TRACE_LOG_PATH, json.dumps(event, ensure_ascii=False) + "\n", append=True)


# ============================================================================
# Token Budget Management
# ============================================================================

@dataclass
class TokenBudgetManager:
    """Track and compact context to stay within 8000 token budget per turn."""
    max_tokens: int = MAX_CONTEXT_TOKENS

    def estimate_tokens(self, text: str) -> int:
        """Rough estimate: 1 token ≈ 4 characters."""
        return len(text) // CHARS_PER_TOKEN_APPROX

    def check_budget(self, messages: list[dict]) -> bool:
        """Check if current messages fit within budget."""
        total = sum(self.estimate_tokens(str(m)) for m in messages)
        return total <= self.max_tokens

    def compact_history(self, messages: list[dict], max_items: int = 5) -> list[dict]:
        """Keep only recent messages + system message to fit budget."""
        system_msgs = [m for m in messages if m.get("role") == "system"]
        other_msgs = [m for m in messages if m.get("role") != "system"]

        # Keep system + last N messages
        compacted = system_msgs + other_msgs[-max_items:]
        return compacted
