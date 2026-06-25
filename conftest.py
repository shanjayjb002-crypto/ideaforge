"""Ensure the repo root is importable so `import scraper...` works under pytest."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
