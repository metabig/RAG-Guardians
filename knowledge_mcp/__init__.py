"""KnowledgeMCP package bootstrap.

Ensures the src layout package is importable when running from repository root.
"""

from pathlib import Path
import sys

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
	sys.path.insert(0, str(_SRC))
