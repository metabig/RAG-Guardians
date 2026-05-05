from pathlib import Path

# Configuration (from main.py)
LM_STUDIO_BASE_URL = "http://127.0.0.1:1234/v1"
LM_STUDIO_API_KEY = "lm-studio"
MODEL_NAME = "google/gemma-4-e4b"

WORKSPACE_ROOT = Path(".").resolve()
SANDBOX_DIR = WORKSPACE_ROOT / "sandbox"
PROMPTS_DIR = WORKSPACE_ROOT / "prompts"

# Constants
MAX_READ_CHARS = 10000  # Strict limit per read
MAX_CONTEXT_TOKENS = 8000  # Budget per turn
CHARS_PER_TOKEN_APPROX = 4  # Approximation for token estimation
TRACE_LOG_PATH = SANDBOX_DIR / "simple_trace.jsonl"