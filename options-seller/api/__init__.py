"""FastAPI backend for the mobile trading-insights app (paper trading only)."""
from pathlib import Path
import sys

# Allow `python -m api.collect_scan` from a fresh clone without an editable install.
_source = str(Path(__file__).resolve().parents[1] / "src")
if _source not in sys.path:
    sys.path.insert(0, _source)
