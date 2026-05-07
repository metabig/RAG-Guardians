import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_CONSECUTIVE_ERRORS = 10
BACKOFF_BASE_SECONDS = 5     # First retry waits 5 s; doubles each time, capped at 40 s.
BACKOFF_MAX_DOUBLINGS = 3    # 5 * 2^3 = 40 s maximum wait.

# ---------------------------------------------------------------------------
# ENVIRONMENT CONFIGURATION
# ---------------------------------------------------------------------------

def _load_dotenv() -> None:
	"""Load KEY=VALUE pairs from .env into process env (without overriding existing vars)."""
	env_file = Path(".env")
	if not env_file.exists():
		return

	for raw_line in env_file.read_text(encoding="utf-8").splitlines():
		line = raw_line.strip()
		if not line or line.startswith("#") or "=" not in line:
			continue
		key, value = line.split("=", 1)
		key = key.strip()
		value = value.strip()
		if not key:
			continue

		# Drop optional surrounding quotes.
		if (value.startswith('"') and value.endswith('"')) or (
			value.startswith("'") and value.endswith("'")
		):
			value = value[1:-1]
		os.environ.setdefault(key, value)


_load_dotenv()

# Generic provider config (OpenAI-compatible endpoint)
OPENAI_BASE_URL = os.getenv(
	"OPENAI_BASE_URL",
	os.getenv("LM_STUDIO_BASE_URL", "http://127.0.0.1:1234/v1"),
)
OPENAI_API_KEY = os.getenv(
	"OPENAI_API_KEY",
	os.getenv("LM_STUDIO_API_KEY", "lm-studio"),
)
MODEL_NAME = os.getenv("MODEL_NAME", "google/gemma-4-e4b")

# Backward-compatible aliases used by existing modules.
LM_STUDIO_BASE_URL = OPENAI_BASE_URL
LM_STUDIO_API_KEY = OPENAI_API_KEY

WORKSPACE_ROOT = Path(".").resolve()
SANDBOX_DIR = WORKSPACE_ROOT / "sandbox"
PROMPTS_DIR = WORKSPACE_ROOT / "prompts"

# ---------------------------------------------------------------------------
# KNOWLEDGE MCP CONFIGURATION
# ---------------------------------------------------------------------------

KNOWLEDGE_DIR = WORKSPACE_ROOT / "knowledge"
KNOWLEDGE_META_DIR = KNOWLEDGE_DIR / ".knowledge_meta"
KNOWLEDGE_PAGE_SIZE = 200  # Default lines per page when reading

# Constants
MAX_READ_CHARS = 10000  # Strict limit per read
MAX_CONTEXT_TOKENS = 4096  # Loaded context window (LM Studio: google/gemma-4-e4b)
CHARS_PER_TOKEN_APPROX = 4  # Approximation for token estimation (English ASCII)
# Gemma-4-e4b is a reasoning model: it consumes ~200 tokens on an internal
# thinking pass before producing output.  Keep this well above that budget.
LLM_MAX_TOKENS = 2048
# Max document chars to feed in a single AI task call.
# Spanish wiki text with URLs tokenizes at ~2.5 chars/token, not 4.
# Budget: 4096 context - 2048 completion - ~300 prompt overhead = ~1748 doc tokens
# 1748 * 2.5 chars/token ≈ 4370 chars; cap conservatively at 3500.
AI_TASK_MAX_DOC_CHARS = 3500
TRACE_LOG_PATH = SANDBOX_DIR / "simple_trace.jsonl"